import json
import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from takebraid.application.decisions import (
    create_decisions,
    decision_plan,
    load_decisions,
    update_decisions,
)
from takebraid.application.ingest import ingest
from takebraid.application.interpretation import interpret_observation
from takebraid.application.preview import render_plan
from takebraid.application.quality import observe_quality
from takebraid.cli import main
from takebraid.domain.decisions import DecisionOverride
from tools.media_validation.fixtures import decode_audio, decode_gray, generate_case
from tools.media_validation.runner import load_cases

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requires media tools"
    ),
]


@pytest.fixture
def prepared(tmp_path):
    case = load_cases()["cases"][0]
    source = generate_case(tmp_path, case, [])
    asset = ingest(source, tmp_path / "project")
    observation, _ = observe_quality(asset, 0)
    p = tmp_path / "policy.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "name": "synthetic-only",
                "calibration": "Fixture only; not camera calibrated",
                "metric": "dark_fraction",
                "enter": "9/10",
                "exit": "4/5",
                "minimum_seconds": "1/25",
                "pad_before_seconds": "0",
                "pad_after_seconds": "0",
            }
        )
    )
    interpretation, _ = interpret_observation(asset, observation, p)
    decision = create_decisions(asset, observation, interpretation)
    return asset, observation, interpretation, decision, source


def identities(output):
    pixels = decode_gray(output, [])
    return [pixels[i] for i in range(0, len(pixels), 64 * 48)]


def test_exclusion_render_restore_and_history_are_source_safe(prepared):
    asset, observation, interpretation, decision, source = prepared
    original = source.read_bytes()
    initial = decision.read_bytes()
    excluded = update_decisions(
        asset, decision, DecisionOverride("set", "exclude", 2, 4, "remove chosen frames")
    )
    plan = decision_plan(asset, excluded, Fraction(25), "source", 1)
    output = render_plan(asset.parents[2], plan)
    assert all(
        abs(a - b) <= 5 for a, b in zip(identities(output), [16, 32, 80, 96, 112, 128], strict=True)
    )
    verification = json.loads((output.parent / "verification.json").read_text())
    assert verification["audio_samples"] == 11520
    assert [i for i, v in enumerate(decode_audio(output, [])) if abs(v) > 5000] == [
        100,
        2020,
        3940,
        5860,
        7780,
        9700,
    ]
    restored = update_decisions(
        asset, excluded, DecisionOverride("restore", None, 2, 4, "restore original evidence")
    )
    rows, _, _ = load_decisions(asset, restored)
    assert not any(r["state"] == "exclude" for r in rows["intervals"])
    restored_output = render_plan(
        asset.parents[2], decision_plan(asset, restored, Fraction(25), "mute", None)
    )
    assert all(
        abs(a - b) <= 5
        for a, b in zip(
            identities(restored_output), [16, 32, 48, 64, 80, 96, 112, 128], strict=True
        )
    )
    assert (
        decision.read_bytes() == initial and excluded.exists() and source.read_bytes() == original
    )
    assert rows["parent"]["path"] == excluded.relative_to(asset.parents[2]).as_posix()
    assert len(rows["overrides"]) == 2
    assert main(["decisions", "show", str(restored), "--asset", str(asset)]) == 0


def test_derived_intervals_parent_and_bound_cuts_are_validated(prepared):
    asset, _, _, decision, _ = prepared
    excluded = update_decisions(
        asset, decision, DecisionOverride("set", "exclude", 2, 4, "explicit")
    )
    plan = decision_plan(asset, excluded, Fraction(25), "mute", None)
    doc = json.loads(plan.read_text())
    doc["timeline"]["cuts"] = doc["timeline"]["cuts"][:1]
    plan.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="bound decisions"):
        render_plan(asset.parents[2], plan)
    record = json.loads(excluded.read_text())
    record["intervals"][0]["state"] = "exclude"
    saved = excluded.read_bytes()
    excluded.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="replayed"):
        load_decisions(asset, excluded)
    excluded.write_bytes(saved)
    decision.write_text(decision.read_text() + " ")
    with pytest.raises(ValueError, match="parent checksum"):
        load_decisions(asset, excluded)


def test_all_excluded_and_outside_project_cannot_make_a_plan(prepared, tmp_path):
    asset, _, _, decision, _ = prepared
    excluded = update_decisions(
        asset, decision, DecisionOverride("set", "exclude", 0, 8, "all excluded")
    )
    with pytest.raises(ValueError, match="empty output"):
        decision_plan(asset, excluded, Fraction(25), "mute", None)
    copy = tmp_path / "copy.json"
    copy.write_bytes(decision.read_bytes())
    with pytest.raises(ValueError, match="identity"):
        load_decisions(asset, copy)


def test_unknown_is_included_and_restoration_recovers_original_uncertainty(prepared):
    from takebraid.domain.quality import QualitySettings

    asset, _, _, _, _ = prepared
    observation, _ = observe_quality(asset, 0, QualitySettings(every=2))
    example = Path(__file__).resolve().parents[1] / "examples/policies/synthetic-bright.json"
    interpretation, _ = interpret_observation(asset, observation, example)
    decision = create_decisions(asset, observation, interpretation)
    doc, _, _ = load_decisions(asset, decision)
    assert {r["state"] for r in doc["intervals"]} == {"keep", "unknown"}
    plan = decision_plan(asset, decision, Fraction(25), "mute", None)
    assert len(json.loads(plan.read_text())["timeline"]["cuts"]) == 1
    excluded = update_decisions(
        asset, decision, DecisionOverride("set", "exclude", 1, 2, "explicit unknown exclusion")
    )
    restored = update_decisions(
        asset, excluded, DecisionOverride("restore", None, 1, 2, "restore uncertainty")
    )
    doc, _, _ = load_decisions(asset, restored)
    row = next(r for r in doc["intervals"] if r["first_frame"] == 1)
    assert row["state"] == row["baseline"] == "unknown"


def test_mutation_during_render_leaves_failed_receipt(prepared, monkeypatch):
    from takebraid.application import preview

    asset, _, _, decision, _ = prepared
    plan = decision_plan(asset, decision, Fraction(25), "mute", None)
    original = preview.render_preview

    def mutate(*args, **kwargs):
        output = original(*args, **kwargs)
        decision.write_text(decision.read_text() + " ")
        return output

    monkeypatch.setattr(preview, "render_preview", mutate)
    with pytest.raises(ValueError, match="history changed|snapshot checksum"):
        render_plan(asset.parents[2], plan)
    receipts = [
        json.loads(p.read_text()) for p in asset.parents[2].glob("stages/*/attempts/*/receipt.json")
    ]
    assert any(
        r["inputs"]["recipe"] == "decision-preview/1" and r["status"] == "failed" for r in receipts
    )


def test_cached_preview_still_checks_decision_dependencies(prepared):
    asset, _, _, decision, _ = prepared
    plan = decision_plan(asset, decision, Fraction(25), "mute", None)
    render_plan(asset.parents[2], plan)
    decision.write_text(decision.read_text() + " ")
    with pytest.raises(ValueError, match="snapshot checksum"):
        render_plan(asset.parents[2], plan)


@pytest.mark.parametrize("error,code", [(OSError("cannot publish"), 1), (KeyboardInterrupt(), 130)])
def test_failed_or_cancelled_publication_preserves_previous_snapshot(
    prepared, monkeypatch, error, code
):
    asset, _, _, decision, _ = prepared
    before = decision.read_bytes()
    count = len(list((asset.parents[2] / "decisions").glob("*/decision.json")))

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("takebraid.application.decisions.write_new_json", fail)
    assert (
        main(
            [
                "decisions",
                "set",
                str(decision),
                "--asset",
                str(asset),
                "--frames",
                "1:2",
                "--state",
                "exclude",
                "--reason",
                "explicit",
            ]
        )
        == code
    )
    assert decision.read_bytes() == before
    assert len(list((asset.parents[2] / "decisions").glob("*/decision.json"))) == count


def test_source_change_prevents_edit_publication(prepared, monkeypatch):
    from takebraid.application import decisions

    asset, _, _, decision, source = prepared
    before = list((asset.parents[2] / "decisions").glob("*/decision.json"))
    original = decisions.resolve_decisions

    def mutate(*args, **kwargs):
        rows = original(*args, **kwargs)
        source.write_bytes(b"changed source")
        return rows

    monkeypatch.setattr(decisions, "resolve_decisions", mutate)
    with pytest.raises(ValueError, match="changed during"):
        update_decisions(asset, decision, DecisionOverride("set", "exclude", 1, 2, "explicit"))
    assert list((asset.parents[2] / "decisions").glob("*/decision.json")) == before
