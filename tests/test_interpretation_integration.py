import json
import shutil
import subprocess
from dataclasses import asdict
from fractions import Fraction as F

import pytest
from test_interpretation import policy

from takebraid.application.ingest import ingest
from takebraid.application.interpretation import interpret_observation
from takebraid.application.quality import observe_quality
from takebraid.cli import main
from takebraid.domain.quality import QualitySettings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requires media tools"
    ),
]


@pytest.fixture
def prepared(tmp_path):
    raw = tmp_path / "pattern.gray"
    raw.write_bytes(b"".join(bytes([v]) * 64 * 48 for v in (128, 255, 255, 128, 255, 128)))
    source = tmp_path / "source.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-copyts",
            "-itsoffset",
            "-0.08",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            "64x48",
            "-framerate",
            "25",
            "-i",
            str(raw),
            "-fps_mode",
            "passthrough",
            "-c:v",
            "ffv1",
            "-avoid_negative_ts",
            "disabled",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    asset = ingest(source, tmp_path / "project")
    observation, _ = observe_quality(asset, 0)
    policy_path = tmp_path / "policy.json"
    p = policy(
        enter=F(9, 10),
        exit=F(4, 5),
        minimum_seconds=F(2, 25),
        pad_before_seconds=F(1, 50),
        pad_after_seconds=F(1, 50),
    )
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                **{k: str(v) if isinstance(v, F) else v for k, v in asdict(p).items()},
            }
        )
    )
    return asset, observation, policy_path, source


def test_policy_produces_exact_candidates_short_run_padding_cache_and_force(prepared):
    asset, observation, p, source = prepared
    original = source.read_bytes()
    path, status = interpret_observation(asset, observation, p)
    assert status == "interpreted"
    r = json.loads(path.read_text())["interpretation"]
    assert [(c["core_in_pts"], c["core_out_pts"]) for c in r["candidates"]] == [(-40, 40)]
    assert [(c["in_pts"], c["out_pts"]) for c in r["candidates"]] == [(-80, 80)]
    assert [(c["in_pts"], c["out_pts"]) for c in r["short_runs"]] == [(80, 120)]
    assert interpret_observation(asset, observation, p)[0] == path
    assert interpret_observation(asset, observation, p, force=True)[0] != path
    newer, _ = observe_quality(asset, 0, force=True)
    assert newer != observation
    assert (
        interpret_observation(asset, observation, p)[0] != path
    )  # latest preserved interpretation pointer
    assert source.read_bytes() == original
    assert main(["interpret", str(observation), "--asset", str(asset), "--policy", str(p)]) == 0


def test_sparse_observation_unknowns_block_duration_and_exit_partial(prepared):
    asset, _, p, _ = prepared
    observation, _ = observe_quality(asset, 0, QualitySettings(every=2))
    path, status = interpret_observation(asset, observation, p)
    assert status == "partial"
    r = json.loads(path.read_text())["interpretation"]
    assert not r["candidates"]
    assert [c["reason"] for c in r["cells"]][1::2] == ["unmeasured_or_unsupported"] * 3
    assert main(["interpret", str(observation), "--asset", str(asset), "--policy", str(p)]) == 2


def test_changed_policy_new_stage_and_damaged_artifacts_fail(prepared):
    asset, observation, p, source = prepared
    first, _ = interpret_observation(asset, observation, p)
    raw = json.loads(p.read_text())
    raw["minimum_seconds"] = "1/25"
    p.write_text(json.dumps(raw))
    second, _ = interpret_observation(asset, observation, p)
    assert first != second
    second.write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        interpret_observation(asset, observation, p)
    observation.write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        interpret_observation(asset, observation, p, force=True)


@pytest.mark.parametrize(
    "error,state", [(ValueError("engine failure"), "failed"), (KeyboardInterrupt(), "cancelled")]
)
def test_failure_and_cancellation_receipts(prepared, monkeypatch, error, state):
    asset, observation, p, _ = prepared

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("takebraid.application.interpretation.interpret_cells", fail)
    with pytest.raises(type(error)):
        interpret_observation(asset, observation, p)
    receipts = [
        json.loads(r.read_text()) for r in asset.parents[2].glob("stages/*/attempts/*/receipt.json")
    ]
    assert any(
        r["inputs"]["recipe"] == "temporal-candidates/1" and r["status"] == state for r in receipts
    )


def test_source_and_policy_mutation_cannot_be_certified(prepared, monkeypatch):
    from takebraid.application import interpretation

    asset, observation, p, source = prepared
    original = interpretation.interpret_cells

    def mutate(*args, **kwargs):
        p.write_text(p.read_text() + " ")
        return original(*args, **kwargs)

    monkeypatch.setattr(interpretation, "interpret_cells", mutate)
    with pytest.raises(ValueError, match="changed during"):
        interpret_observation(asset, observation, p)
    source.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="fingerprint"):
        interpret_observation(asset, observation, p)


def test_motion_interpretation_preserves_unknown_coverage_and_requires_background(tmp_path):
    from takebraid.application.motion import observe_motion
    from takebraid.domain.motion import MotionSettings
    from tools.motion_fixtures import sequence

    raw = tmp_path / "jitter.gray"
    raw.write_bytes(b"".join(sequence("jitter")))
    source = tmp_path / "jitter.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            "96x64",
            "-framerate",
            "25",
            "-i",
            str(raw),
            "-c:v",
            "ffv1",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    asset = ingest(source, tmp_path / "project")
    p = tmp_path / "motion-policy.json"
    settings = policy(
        metric="path_residual_squared",
        enter=F(4),
        exit=F(1),
        minimum_seconds=F(2, 25),
        pad_before_seconds=F(1),
        pad_after_seconds=F(1),
    )
    p.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                **{k: str(v) if isinstance(v, F) else v for k, v in asdict(settings).items()},
            }
        )
    )
    observation, _ = observe_motion(asset, 0)
    output, status = interpret_observation(asset, observation, p)
    assert status == "unknown"
    assert all(
        c["reason"] == "background_not_declared"
        for c in json.loads(output.read_text())["interpretation"]["cells"]
    )
    observation, _ = observe_motion(asset, 0, MotionSettings(background=(0, 0, 96, 64)))
    output, status = interpret_observation(asset, observation, p)
    assert status == "partial"
    r = json.loads(output.read_text())["interpretation"]
    assert [(c["in_pts"], c["out_pts"]) for c in r["candidates"]] == [(40, 120)]
    assert r["cells"][0]["state"] == r["cells"][-1]["state"] == "unknown"


@pytest.mark.parametrize(
    "fps,count,vfr,duration", [("25", 6, True, F(6, 25)), ("30000/1001", 3, False, F(1001, 10000))]
)
def test_interpretation_uses_vfr_and_fractional_final_end(tmp_path, fps, count, vfr, duration):
    raw = tmp_path / "white.gray"
    raw.write_bytes(bytes([255]) * 32 * 32 * count)
    source = tmp_path / "white.mov"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-s",
        "32x32",
        "-framerate",
        fps,
        "-i",
        str(raw),
    ]
    if vfr:
        command += ["-vf", "select=not(eq(n\\,2))"]
    command += ["-fps_mode", "passthrough", "-c:v", "mpeg4", "-q:v", "2", str(source)]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    asset = ingest(source, tmp_path / "project")
    observation, _ = observe_quality(asset, 0)
    settings = policy(minimum_seconds=duration)
    p = tmp_path / "policy.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                **{k: str(v) if isinstance(v, F) else v for k, v in asdict(settings).items()},
            }
        )
    )
    output, status = interpret_observation(asset, observation, p)
    assert status == "interpreted"
    r = json.loads(output.read_text())["interpretation"]
    assert len(r["candidates"]) == 1
    actual = r["candidates"][0]["duration_seconds"]
    assert F(actual["numerator"], actual["denominator"]) == duration


def test_cached_summary_is_recomputed_even_with_a_matching_checksum(prepared):
    from takebraid.adapters.identity import file_digest
    from takebraid.adapters.stages import stage_key

    asset, observation, p, _ = prepared
    output, _ = interpret_observation(asset, observation, p)
    doc = json.loads(output.read_text())
    doc["interpretation"]["candidates"] = []
    output.write_text(json.dumps(doc))
    receipt_path = output.parent / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["output"]["sha256"] = file_digest(output)
    receipt_path.write_text(json.dumps(receipt))
    pointer = asset.parents[2] / "stages" / stage_key(receipt["inputs"]) / "completed.json"
    pointer.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="recomputed evidence"):
        interpret_observation(asset, observation, p)


def test_unsupported_observation_preserves_unknown_reasons(prepared, monkeypatch):
    from dataclasses import replace

    from takebraid.application import analysis

    asset, _, p, _ = prepared
    original = analysis.probe_media

    def hdr(source):
        metadata = original(source)
        return replace(
            metadata,
            streams=tuple(
                replace(s, color_transfer="smpte2084") if s.kind == "video" else s
                for s in metadata.streams
            ),
        )

    monkeypatch.setattr(analysis, "probe_media", hdr)
    observation, status = observe_quality(asset, 0)
    assert status == "unknown"
    output, status = interpret_observation(asset, observation, p)
    assert status == "unknown"
    doc = json.loads(output.read_text())
    assert doc["observation_reasons"] == ["hdr_or_wide_gamut_not_supported"]
    assert not doc["interpretation"]["candidates"]
    assert all(c["state"] == "unknown" for c in doc["interpretation"]["cells"])
