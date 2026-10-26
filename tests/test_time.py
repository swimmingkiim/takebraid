from fractions import Fraction

import pytest

from takebraid.domain.time import SourceRange, TimeBase


def test_ntsc_frame_time_remains_exact_over_one_hour() -> None:
    clock = TimeBase(1, 30000)
    # 107,892 frames at 30000/1001 fps; avoid accumulating rounded seconds.
    assert clock.seconds(107892 * 1001) == Fraction(8999991, 2500)


def test_vfr_duration_uses_pts_not_average_fps() -> None:
    interval = SourceRange("camera-a", 0, 9000, 15345, TimeBase(1, 90000))
    assert interval.duration_seconds == Fraction(141, 2000)


def test_adjacent_half_open_ranges_do_not_add_a_frame() -> None:
    first = SourceRange("a", 0, -1001, 2002, TimeBase(1, 30000))
    second = SourceRange("a", 0, 2002, 5005, TimeBase(1, 30000))
    combined = SourceRange("a", 0, -1001, 5005, TimeBase(1, 30000))
    assert first.duration_seconds + second.duration_seconds == combined.duration_seconds


@pytest.mark.parametrize("start,end", [(0, 0), (4, 3)])
def test_reject_empty_or_reversed_ranges(start: int, end: int) -> None:
    with pytest.raises(ValueError, match="out_pts"):
        SourceRange("a", 0, start, end, TimeBase(1, 25))


@pytest.mark.parametrize("numerator,denominator", [(0, 1), (1, 0), (-1, 25)])
def test_reject_invalid_clocks(numerator: int, denominator: int) -> None:
    with pytest.raises(ValueError):
        TimeBase(numerator, denominator)


@pytest.mark.parametrize("ticks", [True, 1.5])
def test_reject_lossy_or_boolean_timestamps(ticks: object) -> None:
    with pytest.raises(TypeError):
        TimeBase(1, 25).seconds(ticks)  # type: ignore[arg-type]


def test_reject_missing_source_identity() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        SourceRange(" ", 0, 0, 25, TimeBase(1, 25))


def test_reject_negative_stream_index() -> None:
    with pytest.raises(ValueError, match="stream_index"):
        SourceRange("a", -1, 0, 25, TimeBase(1, 25))
