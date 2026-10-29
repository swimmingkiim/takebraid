from fractions import Fraction as F

import pytest

from takebraid.domain.visual import GridDescriptor, describe_gray, match_series, squared_distance


def checker():
    return GridDescriptor(tuple(F(i % 2) for i in range(64)))


def series(asset, descriptor=None, aspect=F(1), frames=1):
    return {
        "asset_id": asset,
        "aspect": aspect,
        "rows": [
            {
                "point": {"frame_index": i, "pts": -40 + i * 80},
                "descriptor": descriptor or checker(),
            }
            for i in range(frames)
        ],
    }


def test_nondivisible_grid_averages_each_pixel_cell_without_float_rounding():
    pixels = bytes(range(81))
    result = describe_gray(pixels, 9, 9)
    assert result.values[0] == 0
    assert result.values[-1] == F(70 + 71 + 79 + 80, 4 * 255)
    assert len(result.values) == 64
    assert squared_distance(result, result) == 0


def test_distance_is_exact_symmetric_and_exposure_sensitive():
    left = checker()
    opposite = GridDescriptor(tuple(1 - v for v in left.values))
    assert squared_distance(left, opposite) == squared_distance(opposite, left) == 1
    assert left.variance == F(1, 4)
    uniform = describe_gray(bytes([128]) * 64, 8, 8)
    assert uniform.variance == 0


@pytest.mark.parametrize(
    "values", [tuple([F(0)] * 63), tuple([0] * 64), tuple([F(2)] * 64), tuple([F(-1)] * 64)]
)
def test_invalid_descriptor_dimensions_types_and_ranges_are_rejected(values):
    with pytest.raises(ValueError):
        GridDescriptor(values)


def test_exact_match_boundary_ties_and_input_order_are_deterministic():
    a, b = series("a", frames=2), series("b", frames=2)
    result = match_series([b, a], F(0), F(1, 100), 2)
    assert result == match_series([a, b], F(0), F(1, 100), 2)
    assert result["matching_pairs"] == 4 and result["truncated_pairs"] == 2
    assert [(r["left"]["frame_index"], r["right"]["frame_index"]) for r in result["matches"]] == [
        (0, 0),
        (0, 1),
    ]
    assert result["matches"][0]["left"]["pts"] == -40


def test_flat_images_and_incompatible_aspect_are_not_duplicate_evidence():
    flat = series("flat", GridDescriptor(tuple([F(0)] * 64)))
    result = match_series([flat, series("textured")], F(1), F(1, 100), 20)
    assert result["matches"] == [] and result["evaluated_pairs"] == 0
    assert result["low_texture_samples"]["flat"] == 1
    result = match_series([series("a"), series("b", aspect=F(4, 3))], F(1), F(1, 100), 20)
    assert result["matches"] == [] and result["incompatible_aspect_pairs"] == 1


@pytest.mark.parametrize(
    "distance,variance,limit",
    [
        (F(-1), F(1, 100), 20),
        (F(2), F(1, 100), 20),
        (F(0), F(0), 20),
        (F(0), F(1, 3), 20),
        (F(0), F(1, 100), True),
        (F(0), F(1, 100), 1001),
    ],
)
def test_comparison_settings_must_be_explicit_and_bounded(distance, variance, limit):
    with pytest.raises(ValueError):
        match_series([series("a"), series("b")], distance, variance, limit)


def test_pair_budget_and_duplicate_content_identity_are_rejected():
    with pytest.raises(ValueError, match="50000"):
        match_series([series("a", frames=225), series("b", frames=225)], F(0), F(1, 100), 20)
    with pytest.raises(ValueError, match="distinct"):
        match_series([series("a"), series("a")], F(0), F(1, 100), 20)


def test_nonzero_distance_threshold_includes_exact_boundary_only():
    left = GridDescriptor(tuple(F(2, 10) if i % 2 else F(8, 10) for i in range(64)))
    right = GridDescriptor(tuple(v + F(1, 10) for v in left.values))
    assert squared_distance(left, right) == F(1, 100)
    inputs = [series("a", left), series("b", right)]
    assert match_series(inputs, F(1, 100), F(1, 1000), 20)["matching_pairs"] == 1
    assert match_series(inputs, F(1, 101), F(1, 1000), 20)["matching_pairs"] == 0
