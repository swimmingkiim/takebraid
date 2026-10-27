import json
from dataclasses import asdict
from fractions import Fraction as F

import pytest

from takebraid.adapters.artifacts import to_json_value
from takebraid.adapters.interpretation import evidence_cells, load_policy
from takebraid.domain.frames import FrameMap, FrameObservation
from takebraid.domain.interpretation import EvidenceCell, TemporalPolicy
from takebraid.domain.time import TimeBase
from takebraid.quality.temporal import interpret_cells


def policy(**kwargs):
    values = dict(
        name="synthetic",
        calibration="synthetic fixture only",
        metric="bright_fraction",
        enter=F(1, 2),
        exit=F(1, 4),
        minimum_seconds=F(1, 100),
        pad_before_seconds=F(0),
        pad_after_seconds=F(0),
    )
    return TemporalPolicy(**(values | kwargs))


def cells(values, boundaries=None):
    boundaries = boundaries or list(range(len(values) + 1))
    return tuple(
        EvidenceCell(a, b, F(v), i)
        if v is not None
        else EvidenceCell(a, b, None, None, "unmeasured")
        for i, (a, b, v) in enumerate(zip(boundaries, boundaries[1:], values, strict=False))
    )


def test_exact_hysteresis_vfr_negative_pts_minimum_and_outward_padding():
    evidence = cells([0, F(3, 5), F(2, 5), F(3, 10), F(1, 4), 0], [-10, 0, 5, 20, 30, 40, 50])
    result = interpret_cells(
        evidence,
        TimeBase(1, 100),
        policy(minimum_seconds=F(3, 10), pad_before_seconds=F(3, 100), pad_after_seconds=F(3, 100)),
    )
    assert result["status"] == "interpreted"
    assert [r["state"] for r in result["cells"]] == [
        "no_trigger",
        "enter",
        "hold",
        "hold",
        "no_trigger",
        "no_trigger",
    ]
    candidate = result["candidates"][0]
    assert (candidate["core_in_pts"], candidate["core_out_pts"]) == (0, 30)
    assert (candidate["in_pts"], candidate["out_pts"]) == (-10, 40)
    assert candidate["duration_seconds"] == F(3, 10)
    assert candidate["evidence_indices"] == [1, 2, 3]


def test_unknown_breaks_hysteresis_duration_and_padding():
    result = interpret_cells(
        cells([1, 1, None, 1, 1]),
        TimeBase(1, 100),
        policy(minimum_seconds=F(3, 100), pad_before_seconds=F(1), pad_after_seconds=F(1)),
    )
    assert result["status"] == "partial"
    assert result["candidates"] == []
    assert [(r["in_pts"], r["out_pts"]) for r in result["short_runs"]] == [(0, 2), (3, 5)]
    accepted = interpret_cells(
        cells([1, 1, None, 1, 1]),
        TimeBase(1, 100),
        policy(minimum_seconds=F(2, 100), pad_before_seconds=F(1), pad_after_seconds=F(1)),
    )
    assert [(r["in_pts"], r["out_pts"]) for r in accepted["candidates"]] == [(0, 2), (3, 5)]


def test_dead_band_never_enters_without_a_trigger_and_low_direction_is_symmetric():
    assert not interpret_cells(cells([F(2, 5)] * 3), TimeBase(1, 100), policy())["candidates"]
    low = policy(metric="laplacian_variance", enter=F(1), exit=F(2))
    result = interpret_cells(cells([F(3, 2), 1, F(3, 2), 2]), TimeBase(1, 100), low)
    assert [(r["core_in_pts"], r["core_out_pts"]) for r in result["candidates"]] == [(1, 3)]
    unknown = interpret_cells(cells([None, None]), TimeBase(1, 100), policy())
    assert unknown["status"] == "unknown" and not unknown["candidates"]


def test_sparse_quality_never_holds_a_sample_across_unmeasured_frames():
    frame_map = FrameMap(
        "asset",
        0,
        TimeBase(1, 100),
        (FrameObservation(0, 1), FrameObservation(1, 1), FrameObservation(2, 1)),
    )
    raw = {
        "observations": [
            {"frame_index": 0, "metrics": {"bright_fraction": {"numerator": 1, "denominator": 1}}},
            {"frame_index": 2, "metrics": {"bright_fraction": {"numerator": 1, "denominator": 1}}},
        ]
    }
    evidence = evidence_cells(raw, frame_map, policy())
    assert [c.value for c in evidence] == [1, None, 1]
    assert (
        interpret_cells(evidence, frame_map.time_base, policy(minimum_seconds=F(2, 100)))[
            "candidates"
        ]
        == []
    )


def test_motion_requires_background_and_residual_time_is_a_single_frame_cell():
    frame_map = FrameMap(
        "asset", 0, TimeBase(1, 100), tuple(FrameObservation(i, 1) for i in range(4))
    )
    p = policy(metric="path_residual_squared", enter=F(4), exit=F(1))
    raw = {
        "model_role": "dominant_image_translation",
        "path": [
            {
                "residual_at_frame": 1,
                "previous_sample_residual": [
                    {"numerator": 2, "denominator": 1},
                    {"numerator": 0, "denominator": 1},
                ],
            }
        ],
    }
    assert all(
        c.value is None and c.reason == "background_not_declared"
        for c in evidence_cells(raw, frame_map, p)
    )
    raw["model_role"] = "declared_background_translation"
    assert [c.value for c in evidence_cells(raw, frame_map, p)] == [None, 4, None, None]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"calibration": ""},
        {"metric": "speed"},
        {"enter": F(1, 4)},
        {"enter": F(2)},
        {"minimum_seconds": F(0)},
        {"pad_after_seconds": F(61)},
        {"enter": 0.5},
    ],
)
def test_invalid_or_implicit_policy_is_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        policy(**kwargs)


def test_policy_requires_explicit_rational_strings(tmp_path):
    path = tmp_path / "policy.json"
    raw = {
        "schema_version": "0.1",
        **{k: str(v) if isinstance(v, F) else v for k, v in asdict(policy()).items()},
    }
    path.write_text(json.dumps(raw))
    assert load_policy(path) == policy()
    raw["enter"] = 0.5
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="rational strings"):
        load_policy(path)


def test_partition_is_required_and_padding_does_not_merge_separate_core_runs():
    with pytest.raises(ValueError, match="partition"):
        interpret_cells(
            (EvidenceCell(0, 1, F(1), 0), EvidenceCell(2, 3, F(1), 1)), TimeBase(1, 100), policy()
        )
    result = interpret_cells(
        cells([1, 0, 1]), TimeBase(1, 100), policy(pad_before_seconds=F(1), pad_after_seconds=F(1))
    )
    assert [(r["core_in_pts"], r["core_out_pts"]) for r in result["candidates"]] == [(0, 1), (2, 3)]
    assert all((r["in_pts"], r["out_pts"]) == (0, 3) for r in result["candidates"])
    assert to_json_value(result)["candidates"][0]["duration_seconds"] == {
        "numerator": 1,
        "denominator": 100,
    }


def test_unknown_resets_latched_state_before_dead_band():
    result = interpret_cells(cells([1, None, F(2, 5)]), TimeBase(1, 100), policy())
    assert [c["state"] for c in result["cells"]] == ["enter", "unknown", "no_trigger"]
    assert [(c["core_in_pts"], c["core_out_pts"]) for c in result["candidates"]] == [(0, 1)]


@pytest.mark.parametrize("invalid", ["1e999999999999999999", "nan", "-1", "1/0", True])
def test_policy_rejects_nonfinite_exponent_or_invalid_rational(tmp_path, invalid):
    path = tmp_path / "bad.json"
    raw = {
        "schema_version": "0.1",
        **{k: str(v) if isinstance(v, F) else v for k, v in asdict(policy()).items()},
    }
    raw["enter"] = invalid
    path.write_text(json.dumps(raw))
    with pytest.raises((ValueError, ZeroDivisionError)):
        load_policy(path)


def test_completed_artifact_requires_receipt_checksum_identity_and_project(tmp_path):
    from takebraid.adapters.artifacts import write_new_json
    from takebraid.adapters.stages import StageAttempt, completed_artifact

    root = tmp_path / "project"
    inputs = {"recipe": "test-observation/1"}
    with StageAttempt(root, inputs) as attempt:
        output = attempt.directory / "observation.json"
        write_new_json(output, {"schema_version": "0.1", "test": True})
        attempt.complete(output)
    assert completed_artifact(root, output) == inputs
    (tmp_path / "other").mkdir()
    with pytest.raises(ValueError, match="belong"):
        completed_artifact(tmp_path / "other", output)
    receipt = output.parent / "receipt.json"
    original = receipt.read_text()
    doc = json.loads(original)
    doc["status"] = "failed"
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="Invalid completed"):
        completed_artifact(root, output)
    receipt.write_text(original)
    output.write_text("{}")
    with pytest.raises(ValueError, match="Invalid completed"):
        completed_artifact(root, output)
