from fractions import Fraction

import pytest

from takebraid.domain.frames import FrameMap, FrameObservation, map_proxy_samples
from takebraid.domain.time import SourceRange, TimeBase


def frame_map(points=(-40, 0, 80), durations=(40, 80, 40)):
    return FrameMap(
        "asset",
        2,
        TimeBase(1, 1000),
        tuple(
            FrameObservation(pts, duration) for pts, duration in zip(points, durations, strict=True)
        ),
    )


def test_signed_vfr_boundaries_and_final_end():
    result = frame_map()
    assert result.status == "ready"
    assert result.cadence == "variable_pts_intervals"
    assert result.boundaries() == (-40, 0, 80, 120)
    interval = SourceRange("asset", 2, -40, 120, TimeBase(1, 1000))
    result.validate_range(interval)
    assert interval.duration_seconds == Fraction(4, 25)


@pytest.mark.parametrize(
    "points,durations,code",
    [
        ((0, None), (40, 40), "missing_pts"),
        ((0, 0), (40, 40), "non_increasing_pts"),
        ((40, 0), (40, 40), "non_increasing_pts"),
        ((0, 40), (40, None), "final_duration_unknown"),
        ((0, 40), (40, 0), "invalid_duration"),
        ((), (), "no_decoded_frames"),
    ],
)
def test_unsupported_timing_never_produces_editable_bounds(points, durations, code):
    result = frame_map(points, durations)
    assert result.status == "unsupported"
    assert code in {issue.code for issue in result.issues}
    with pytest.raises(ValueError, match="unsupported"):
        result.boundaries()


def test_duration_gap_or_overlap_needs_review_not_silent_repair():
    for duration in (20, 60):
        result = frame_map((0, 40), (duration, 40))
        assert result.status == "review_required"
        assert result.issues[0].code == "reported_duration_conflict"
        with pytest.raises(ValueError, match="review_required"):
            result.boundaries()


def test_missing_internal_duration_uses_observed_next_pts_but_not_fps():
    result = frame_map((0, 80), (None, 40))
    assert result.status == "ready"
    assert result.boundaries() == (0, 80, 120)


@pytest.mark.parametrize(
    "interval",
    [
        SourceRange("other", 2, 0, 80, TimeBase(1, 1000)),
        SourceRange("asset", 1, 0, 80, TimeBase(1, 1000)),
        SourceRange("asset", 2, 0, 80, TimeBase(1, 25)),
        SourceRange("asset", 2, 1, 80, TimeBase(1, 1000)),
        SourceRange("asset", 2, 80, 121, TimeBase(1, 1000)),
    ],
)
def test_range_rejects_wrong_identity_clock_or_non_frame_boundary(interval):
    with pytest.raises(ValueError):
        frame_map().validate_range(interval)


def test_best_effort_timestamp_is_not_used_to_repair_missing_pts():
    result = FrameMap("asset", 0, TimeBase(1, 25), (FrameObservation(None, 1, 0),))
    assert result.status == "unsupported"
    assert result.frames[0].pts is None


def test_proxy_mapping_uses_exact_elapsed_time_and_vfr_intervals():
    # Explicit offset: proxy tick 100 corresponds to source tick -40.
    samples = map_proxy_samples(
        frame_map(),
        (100, 101, 102, 103),
        TimeBase(1, 25),
        source_origin_pts=-40,
        proxy_origin_pts=100,
    )
    assert [sample.source_frame_index for sample in samples] == [0, 1, 1, 2]
    assert [sample.source_pts for sample in samples] == [-40, 0, 0, 80]


@pytest.mark.parametrize("samples", [(99,), (104,), (100, 100), (101, 100)])
def test_proxy_mapping_never_clamps_or_accepts_unordered_samples(samples):
    with pytest.raises(ValueError):
        map_proxy_samples(
            frame_map(), samples, TimeBase(1, 25), source_origin_pts=-40, proxy_origin_pts=100
        )


def test_proxy_mapping_refuses_uncertain_source_map():
    with pytest.raises(ValueError, match="review_required"):
        map_proxy_samples(
            frame_map((0, 40), (20, 40)),
            (0,),
            TimeBase(1, 25),
            source_origin_pts=0,
            proxy_origin_pts=0,
        )


def test_frame_records_reject_float_and_boolean_timestamps():
    with pytest.raises(TypeError):
        FrameObservation(True, 1)
    with pytest.raises(TypeError):
        FrameObservation(0, 1.5)
