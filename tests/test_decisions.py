import pytest

from takebraid.domain.decisions import DecisionOverride, included_cuts, resolve_decisions
from takebraid.domain.frames import FrameMap, FrameObservation
from takebraid.domain.time import TimeBase


def evidence():
    frame_map = FrameMap(
        "asset", 0, TimeBase(1, 1000), tuple(FrameObservation(-80 + i * 40, 40) for i in range(6))
    )
    bounds = frame_map.boundaries()
    interpretation = {
        "cells": [
            {
                "in_pts": bounds[i],
                "out_pts": bounds[i + 1],
                "state": "unknown" if i == 5 else "no_trigger",
            }
            for i in range(6)
        ],
        "candidates": [{"in_pts": -40, "out_pts": 40}],
    }
    return frame_map, interpretation


def test_baseline_preserves_review_unknown_and_never_excludes():
    frame_map, interpretation = evidence()
    rows = resolve_decisions(frame_map, interpretation, ())
    assert [r["state"] for r in rows] == ["keep", "review", "keep", "unknown"]
    assert [(r["first_frame"], r["end_frame"]) for r in rows] == [(0, 1), (1, 3), (3, 5), (5, 6)]
    assert included_cuts(rows) == ((0, 6),)


def test_explicit_exclude_restore_and_last_override_preserve_baseline_and_history():
    frame_map, interpretation = evidence()
    excluded = DecisionOverride("set", "exclude", 1, 6, "user excludes")
    rows = resolve_decisions(frame_map, interpretation, (excluded,))
    assert included_cuts(rows) == ((0, 1),)
    restored = DecisionOverride("restore", None, 2, 6, "restore inclusion and warnings")
    rows = resolve_decisions(frame_map, interpretation, (excluded, restored))
    assert included_cuts(rows) == ((0, 1), (2, 6))
    assert [r["state"] for r in rows] == ["keep", "exclude", "review", "keep", "unknown"]
    assert rows[-1]["override_index"] == 1
    kept = DecisionOverride("set", "keep", 5, 6, "manual keep despite unknown")
    rows = resolve_decisions(frame_map, interpretation, (excluded, restored, kept))
    assert rows[-1]["state"] == "keep" and rows[-1]["baseline"] == "unknown"
    assert len((excluded, restored, kept)) == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"first_frame": True},
        {"first_frame": -1},
        {"end_frame": 0},
        {"reason": ""},
        {"action": "delete"},
        {"state": "bad"},
        {"action": "restore", "state": "keep"},
    ],
)
def test_invalid_override_fails(kwargs):
    values = dict(action="set", state="exclude", first_frame=0, end_frame=1, reason="explicit")
    with pytest.raises((ValueError, TypeError)):
        DecisionOverride(**(values | kwargs))


def test_empty_output_bounds_and_history_limit_are_enforced():
    frame_map, interpretation = evidence()
    with pytest.raises(ValueError, match="source frame"):
        resolve_decisions(
            frame_map, interpretation, (DecisionOverride("set", "keep", 0, 7, "too far"),)
        )
    with pytest.raises(ValueError, match="100"):
        resolve_decisions(
            frame_map, interpretation, (DecisionOverride("set", "keep", 0, 1, "many"),) * 101
        )
    rows = resolve_decisions(
        frame_map, interpretation, (DecisionOverride("set", "exclude", 0, 6, "exclude all"),)
    )
    with pytest.raises(ValueError, match="empty output"):
        included_cuts(rows)


def test_candidate_cannot_cover_unknown_or_unmapped_evidence():
    frame_map, interpretation = evidence()
    interpretation["candidates"] = [{"in_pts": 120, "out_pts": 160}]
    with pytest.raises(ValueError, match="unknown"):
        resolve_decisions(frame_map, interpretation, ())
    interpretation["cells"][0]["out_pts"] = 1
    with pytest.raises(ValueError, match="boundaries"):
        resolve_decisions(frame_map, interpretation, ())
