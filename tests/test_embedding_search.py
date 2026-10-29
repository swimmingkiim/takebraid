import math

import pytest

from takebraid.domain.embeddings import cosine_similarity, search_series


def series(asset, vectors):
    return {
        "asset_id": asset,
        "rows": [
            {"point": {"frame_index": i, "pts": -100 + i * i * 20}, "values": values}
            for i, values in enumerate(vectors)
        ],
    }


def test_cosine_is_normalized_signed_and_clamped_for_floating_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1
    assert cosine_similarity([0.6, 0.8], [0.8, 0.6]) == pytest.approx(0.96)
    assert cosine_similarity([0.6, 0.8], [0.60000006, 0.80000008]) == pytest.approx(1)


def test_missing_numeric_coverage_is_not_an_orthogonal_or_zero_match():
    a, b = series("a", [[1.0, 0.0], None]), series("b", [None, [1.0, 0.0]])
    result = search_series([a, b], 2, 1.0, 20)
    assert result["possible_pairs"] == 4 and result["evaluated_pairs"] == 1
    assert result["unknown_pairs"] == 3
    assert result["unknown_samples"] == {"a": 1, "b": 1}
    assert result["matches"][0]["left"]["pts"] == -100
    assert result["matches"][0]["right"]["frame_index"] == 1


def test_threshold_ties_truncation_and_input_order_are_deterministic():
    a = series("a", [[1.0, 0.0], [0.0, 1.0]])
    b = series("b", [[0.0, 1.0], [1.0, 0.0]])
    result = search_series([b, a], 2, 0.0, 1)
    assert result == search_series([a, b], 2, 0.0, 1)
    assert result["matching_pairs"] == 4 and result["truncated_pairs"] == 3
    assert result["matches"][0]["left"]["frame_index"] == 0
    assert result["matches"][0]["right"]["frame_index"] == 1
    assert search_series([a, b], 2, 1.0, 20)["matching_pairs"] == 2


@pytest.mark.parametrize(
    "threshold,limit,dimensions",
    [
        (float("nan"), 20, 2),
        (float("inf"), 20, 2),
        (1.1, 20, 2),
        (-1.1, 20, 2),
        (True, 20, 2),
        (0.0, True, 2),
        (0.0, 1001, 2),
        (0.0, 20, 0),
        (0.0, 20, 4097),
    ],
)
def test_settings_are_explicit_finite_and_bounded(threshold, limit, dimensions):
    with pytest.raises(ValueError):
        search_series([series("a", []), series("b", [])], dimensions, threshold, limit)


def test_pair_sample_and_coordinate_budgets_are_enforced_before_scoring():
    with pytest.raises(ValueError, match="50000"):
        search_series([series("a", [None] * 225), series("b", [None] * 225)], 2, 0.0, 20)
    with pytest.raises(ValueError, match="2000000"):
        search_series([series("a", [None] * 1000), series("b", [None] * 1000)], 4096, 0.0, 20)
    with pytest.raises(ValueError, match="8000000"):
        search_series([series("a", [None] * 100), series("b", [None] * 100)], 1024, 0.0, 20)
    with pytest.raises(ValueError, match="distinct"):
        search_series([series("a", []), series("a", [])], 2, 0.0, 20)


@pytest.mark.parametrize("vector", [[0.0, 0.0], [math.nan, 0.0], [1, 0], [1.0]])
def test_invalid_vectors_never_enter_scores(vector):
    with pytest.raises(ValueError):
        search_series([series("a", [vector]), series("b", [[1.0, 0.0]])], 2, 0.0, 20)
