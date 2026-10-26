"""Normalized probe observations, independent of media tools and storage."""

from dataclasses import dataclass
from fractions import Fraction

from takebraid.domain.time import TimeBase


@dataclass(frozen=True)
class StreamMetadata:
    index: int
    kind: str
    codec: str | None
    time_base: TimeBase | None
    start_pts: int | None
    duration_ts: int | None
    reported_start_seconds: Fraction | None
    reported_duration_seconds: Fraction | None
    average_frame_rate: Fraction | None
    nominal_frame_rate: Fraction | None
    width: int | None
    height: int | None
    rotation_degrees: Fraction | None
    display_matrix: str | None
    pixel_format: str | None
    color_range: str | None
    color_space: str | None
    color_transfer: str | None
    color_primaries: str | None
    sample_rate: int | None
    channels: int | None
    channel_layout: str | None
    attached_picture: bool


@dataclass(frozen=True)
class ProbeMetadata:
    format_name: str
    reported_start_seconds: Fraction | None
    reported_duration_seconds: Fraction | None
    streams: tuple[StreamMetadata, ...]
    ffprobe_version: str
    warnings: tuple[str, ...]
