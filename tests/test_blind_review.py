import copy

import pytest

from takebraid.domain.evaluation import LabelInterval
from tools.blind_review import merge_votes, review_votes


def packet():
    return {
        "tasks": [{"id": "task", "media_id": "media"}],
        "media": {"media": {"images": [{}] * 4}},
    }


def review():
    return {
        "reviewer": "rater-a",
        "packet_sha256": "a" * 64,
        "reviewer_kind": "human",
        "independent_before_predictions": True,
        "tasks": [
            {"id": "task", "intervals": [{"first_frame": 0, "end_frame": 4, "truth": "unknown"}]}
        ],
    }


def test_explicit_unknown_is_preserved_as_a_review_vote():
    assert review_votes(review(), packet(), "a" * 64) == ("rater-a", {"task": ["unknown"] * 4})


@pytest.mark.parametrize(
    "key,value",
    [
        ("reviewer", "../rater"),
        ("reviewer", ""),
        ("packet_sha256", "b" * 64),
        ("reviewer_kind", "assistant"),
        ("independent_before_predictions", False),
        ("independent_before_predictions", 1),
        ("tasks", []),
        ("tasks", [review()["tasks"][0]] * 2),
    ],
)
def test_collection_rejects_invalid_provenance_or_missing_tasks(key, value):
    doc = review()
    doc[key] = value
    with pytest.raises(ValueError):
        review_votes(doc, packet(), "a" * 64)


@pytest.mark.parametrize(
    "intervals",
    [
        [],
        [{"first_frame": 1, "end_frame": 4, "truth": "normal"}],
        [{"first_frame": 0, "end_frame": 3, "truth": "normal"}],
        [{"first_frame": 0, "end_frame": 5, "truth": "normal"}],
        [{"first_frame": False, "end_frame": 4, "truth": "normal"}],
        [{"first_frame": 0, "end_frame": 4.0, "truth": "normal"}],
        [{"first_frame": 0, "end_frame": 4, "truth": None}],
        [
            {"first_frame": 0, "end_frame": 3, "truth": "normal"},
            {"first_frame": 2, "end_frame": 4, "truth": "defect"},
        ],
    ],
)
def test_collection_requires_a_complete_nonoverlapping_integer_partition(intervals):
    doc = copy.deepcopy(review())
    doc["tasks"][0]["intervals"] = intervals
    with pytest.raises(ValueError):
        review_votes(doc, packet(), "a" * 64)


def test_distinct_partitions_are_combined_with_disagreement_not_majority_labels():
    labels = merge_votes(
        [
            ("a", {"task": ["normal", "normal", "defect", "unknown"]}),
            ("b", {"task": ["normal", "defect", "defect", "unknown"]}),
        ]
    )["task"]
    assert [(row["first_frame"], row["end_frame"]) for row in labels] == [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
    ]
    assert labels[1]["votes"] == {"a": "normal", "b": "defect"}
    assert LabelInterval(1, 2, tuple(labels[1]["votes"].values())).consensus == "unknown"
    assert labels[-1]["votes"] == {"a": "unknown", "b": "unknown"}


@pytest.mark.parametrize(
    "reviews",
    [
        [("a", {"task": ["normal"]})],
        [("a", {"task": ["normal"]}), ("a", {"task": ["normal"]})],
        [("a", {"task": ["normal"]}), ("b", {"task": ["normal", "normal"]})],
    ],
)
def test_duplicate_reviewers_and_different_clocks_are_rejected(reviews):
    with pytest.raises(ValueError):
        merge_votes(reviews)
