from fractions import Fraction as F

import pytest

from takebraid.domain.evaluation import LabelInterval, score_labels
from takebraid.domain.frames import FrameMap, FrameObservation
from takebraid.domain.time import TimeBase


def example():
    frame_map = FrameMap(
        "asset",
        0,
        TimeBase(1, 100),
        (
            FrameObservation(-10, 10),
            FrameObservation(0, 20),
            FrameObservation(20, 30),
            FrameObservation(50, 40),
        ),
    )
    bounds = frame_map.boundaries()
    interpretation = {
        "cells": [
            {
                "in_pts": bounds[i],
                "out_pts": bounds[i + 1],
                "state": "unknown" if i == 1 else "no_trigger",
            }
            for i in range(4)
        ],
        "candidates": [
            {"core_in_pts": -10, "core_out_pts": 0},
            {"core_in_pts": 20, "core_out_pts": 50},
        ],
    }
    labels = (LabelInterval(0, 2, ("defect", "defect")), LabelInterval(2, 4, ("normal", "normal")))
    return frame_map, interpretation, labels


def test_duration_weighted_metrics_count_unknown_defect_in_all_label_recall():
    frame_map, interpretation, labels = example()
    r = score_labels(frame_map, labels, interpretation)
    t = r["durations"]
    assert t["source_seconds"] == 1
    assert t["true_positive_seconds"] == F(1, 10)
    assert t["false_positive_seconds"] == F(3, 10)
    assert t["true_negative_seconds"] == F(2, 5)
    assert t["unknown_on_defect_seconds"] == F(1, 5)
    assert r["ratios"]["precision"] == F(1, 4)
    assert r["ratios"]["recall_all_labeled_defect"] == F(1, 3)
    assert r["ratios"]["recall_observed_defect"] == 1
    assert r["ratios"]["prediction_unknown_rate"] == F(1, 5)
    assert r["ratios"]["normal_exclusion_rate"] is None
    assert r["decision_evaluated"] is False


def test_explicit_user_exclusions_are_scored_separately_from_review_candidates():
    frame_map, interpretation, labels = example()
    decisions = [
        {"first_frame": 0, "end_frame": 3, "state": "keep"},
        {"first_frame": 3, "end_frame": 4, "state": "exclude"},
    ]
    r = score_labels(frame_map, labels, interpretation, decisions)
    assert r["durations"]["false_positive_seconds"] == F(3, 10)
    assert r["durations"]["excluded_normal_seconds"] == F(2, 5)
    assert r["ratios"]["normal_exclusion_rate"] == F(4, 7)
    assert r["durations"]["decision_coverage_seconds"] == 1


def test_disagreement_unknown_labels_are_not_turned_into_negatives():
    frame_map, interpretation, _ = example()
    labels = (
        LabelInterval(0, 1, ("defect", "normal")),
        LabelInterval(1, 2, ("unknown", "unknown")),
        LabelInterval(2, 4, ("normal", "normal")),
    )
    r = score_labels(frame_map, labels, interpretation)
    assert r["disagreement_frames"] == 1
    assert r["durations"]["label_unknown_seconds"] == F(3, 10)
    assert r["durations"]["candidate_label_unknown_seconds"] == F(1, 10)
    assert r["ratios"]["recall_all_labeled_defect"] is None
    assert r["ratios"]["precision"] == 0


def test_empty_positive_denominators_are_null_not_perfect_scores():
    frame_map, interpretation, _ = example()
    interpretation["candidates"] = []
    labels = (LabelInterval(0, 4, ("normal", "normal")),)
    r = score_labels(frame_map, labels, interpretation)
    assert r["ratios"]["precision"] is None
    assert r["ratios"]["recall_all_labeled_defect"] is None


@pytest.mark.parametrize(
    "labels",
    [
        (LabelInterval(1, 4, ("normal", "normal")),),
        (LabelInterval(0, 3, ("normal", "normal")),),
        (LabelInterval(0, 5, ("normal", "normal")),),
    ],
)
def test_labels_must_fully_partition_source(labels):
    frame_map, interpretation, _ = example()
    with pytest.raises(ValueError, match="Labels"):
        score_labels(frame_map, labels, interpretation)


def test_candidates_cannot_consume_unknown_prediction_cells():
    frame_map, interpretation, labels = example()
    interpretation["candidates"] = [{"core_in_pts": 0, "core_out_pts": 20}]
    with pytest.raises(ValueError, match="observed coverage"):
        score_labels(frame_map, labels, interpretation)


def test_cohort_aggregation_uses_duration_totals_not_average_ratios():
    from takebraid.application.evaluation import _aggregate

    frame_map, interpretation, labels = example()
    first = score_labels(frame_map, labels, interpretation)
    source = FrameMap("second", 0, TimeBase(1, 100), (FrameObservation(0, 100),))
    second = score_labels(
        source,
        (LabelInterval(0, 1, ("defect", "defect")),),
        {
            "cells": [{"in_pts": 0, "out_pts": 100, "state": "no_trigger"}],
            "candidates": [{"core_in_pts": 0, "core_out_pts": 100}],
        },
    )
    r = _aggregate(
        [
            {"project_id": "a", "shoot_id": "a-1", "score": first},
            {"project_id": "b", "shoot_id": "b-1", "score": second},
        ]
    )
    assert r["ratios"]["precision"] == F(11, 14)
    assert r["ratios"]["recall_all_labeled_defect"] == F(11, 13)
    assert r["projects"] == r["shoots"] == 2
    assert r["decision_entries"] == 0 and r["ratios"]["normal_exclusion_rate"] is None
