"""Exact source time values; source intervals are half-open [in, out)."""

from dataclasses import dataclass
from fractions import Fraction


def _require_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")


@dataclass(frozen=True)
class TimeBase:
    """Seconds per source timestamp tick, as reported by the source stream."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        _require_int(self.numerator, "numerator")
        _require_int(self.denominator, "denominator")
        if self.numerator <= 0 or self.denominator <= 0:
            raise ValueError("time base components must be positive")

    def seconds(self, ticks: int) -> Fraction:
        _require_int(ticks, "ticks")
        return ticks * Fraction(self.numerator, self.denominator)


@dataclass(frozen=True)
class SourceRange:
    """A nonempty range on one asset stream's PTS clock.

    Negative PTS values are valid. This value alone cannot validate that endpoints
    are inside a media stream or lie on decoded frame boundaries; ingest supplies
    those bounds and the frame PTS map in a later milestone.
    """

    asset_id: str
    stream_index: int
    in_pts: int
    out_pts: int
    time_base: TimeBase

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("asset_id must be a nonempty string")
        _require_int(self.stream_index, "stream_index")
        _require_int(self.in_pts, "in_pts")
        _require_int(self.out_pts, "out_pts")
        if self.stream_index < 0:
            raise ValueError("stream_index must be nonnegative")
        if self.out_pts <= self.in_pts:
            raise ValueError("out_pts must be greater than in_pts")
        if not isinstance(self.time_base, TimeBase):
            raise TypeError("time_base must be a TimeBase")

    @property
    def duration_seconds(self) -> Fraction:
        return self.time_base.seconds(self.out_pts - self.in_pts)
