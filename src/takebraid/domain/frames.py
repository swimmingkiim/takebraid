"""Decoded presentation observations and conservative, exact source boundaries."""

from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction

from takebraid.domain.time import SourceRange, TimeBase, _require_int


@dataclass(frozen=True)
class FrameObservation:
    pts: int | None
    duration: int | None
    best_effort_timestamp: int | None = None

    def __post_init__(self) -> None:
        for name in ("pts", "duration", "best_effort_timestamp"):
            value = getattr(self, name)
            if value is not None:
                _require_int(value, name)


@dataclass(frozen=True)
class TimingIssue:
    code: str
    frame_index: int | None


@dataclass(frozen=True)
class FrameMap:
    asset_id: str
    stream_index: int
    time_base: TimeBase
    frames: tuple[FrameObservation, ...]

    def __post_init__(self) -> None:
        # Reuse source identity/clock validation; this does not assert actual bounds.
        SourceRange(self.asset_id, self.stream_index, 0, 1, self.time_base)
        if not isinstance(self.frames, tuple) or not all(
            isinstance(frame, FrameObservation) for frame in self.frames
        ):
            raise TypeError("frames must be a tuple of FrameObservation values")

    @property
    def issues(self) -> tuple[TimingIssue, ...]:
        issues = []
        if not self.frames:
            return (TimingIssue("no_decoded_frames", None),)
        for index, frame in enumerate(self.frames):
            if frame.pts is None:
                issues.append(TimingIssue("missing_pts", index))
            if frame.duration is not None and frame.duration <= 0:
                issues.append(TimingIssue("invalid_duration", index))
            if index:
                previous = self.frames[index - 1]
                if previous.pts is not None and frame.pts is not None:
                    delta = frame.pts - previous.pts
                    if delta <= 0:
                        issues.append(TimingIssue("non_increasing_pts", index))
                    elif previous.duration is not None and previous.duration > 0:
                        if delta != previous.duration:
                            issues.append(TimingIssue("reported_duration_conflict", index - 1))
        last = self.frames[-1]
        if last.duration is None or last.duration <= 0:
            issues.append(TimingIssue("final_duration_unknown", len(self.frames) - 1))
        return tuple(issues)

    @property
    def status(self) -> str:
        codes = {issue.code for issue in self.issues}
        if codes - {"reported_duration_conflict"}:
            return "unsupported"
        return "review_required" if codes else "ready"

    @property
    def presentation_end_pts(self) -> int | None:
        if not self.frames:
            return None
        last = self.frames[-1]
        if last.pts is None or last.duration is None or last.duration <= 0:
            return None
        return last.pts + last.duration

    @property
    def cadence(self) -> str:
        points = [frame.pts for frame in self.frames]
        if len(points) < 2 or any(point is None for point in points):
            return "unknown"
        deltas = [right - left for left, right in zip(points, points[1:], strict=False)]
        if any(delta <= 0 for delta in deltas):
            return "unknown"
        return "uniform_pts_intervals" if len(set(deltas)) == 1 else "variable_pts_intervals"

    def boundaries(self) -> tuple[int, ...]:
        if self.status != "ready":
            raise ValueError(f"Frame map is {self.status}; review/repair timing before editing")
        return tuple(frame.pts for frame in self.frames) + (self.presentation_end_pts,)

    def validate_range(self, interval: SourceRange) -> None:
        if (
            interval.asset_id != self.asset_id
            or interval.stream_index != self.stream_index
            or interval.time_base != self.time_base
        ):
            raise ValueError("Source range does not belong to this asset, stream and clock")
        boundaries = self.boundaries()
        if interval.in_pts not in boundaries[:-1] or interval.out_pts not in boundaries:
            raise ValueError("Source range endpoints must be decoded presentation boundaries")


@dataclass(frozen=True)
class ProxySample:
    proxy_pts: int
    source_frame_index: int
    source_pts: int


def map_proxy_samples(
    source: FrameMap,
    proxy_pts: tuple[int, ...],
    proxy_time_base: TimeBase,
    *,
    source_origin_pts: int,
    proxy_origin_pts: int,
) -> tuple[ProxySample, ...]:
    """Map verified proxy sample times through an explicit 1x clock origin.

    Only for a declared normal-speed, unretimed proxy. This does not infer that
    relationship from media, nor create a proxy. No interpolation or clamping.
    """
    _require_int(source_origin_pts, "source_origin_pts")
    _require_int(proxy_origin_pts, "proxy_origin_pts")
    boundaries = source.boundaries()
    result = []
    previous = None
    for pts in proxy_pts:
        _require_int(pts, "proxy_pts")
        if previous is not None and pts <= previous:
            raise ValueError("Proxy PTS must be strictly increasing")
        previous = pts
        seconds = proxy_time_base.seconds(pts - proxy_origin_pts)
        position = Fraction(source_origin_pts) + seconds / source.time_base.seconds(1)
        if position < boundaries[0] or position >= boundaries[-1]:
            raise ValueError("Proxy sample is outside the half-open source presentation range")
        index = bisect_right(boundaries, position) - 1
        result.append(ProxySample(pts, index, boundaries[index]))
    return tuple(result)
