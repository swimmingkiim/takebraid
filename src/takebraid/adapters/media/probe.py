"""Read local media metadata without trusting or reconstructing frame positions."""

import json
import math
import re
import subprocess
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from takebraid.domain.metadata import ProbeMetadata, StreamMetadata
from takebraid.domain.time import TimeBase


class ProbeError(ValueError):
    """Unusable media or malformed probe output with an actionable explanation."""


def _object(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise ProbeError(f"{field} must be a JSON object")
    return value


def _text(value: object, field: str) -> str | None:
    if value is None or value == "N/A":
        return None
    if not isinstance(value, str) or not value:
        raise ProbeError(f"{field} must be a nonempty string")
    return value


def _integer(value: object, field: str, minimum: int | None = None) -> int | None:
    if value is None or value == "N/A":
        return None
    if isinstance(value, bool) or not re.fullmatch(r"-?\d+", str(value)):
        raise ProbeError(f"{field} must be an integer")
    result = int(value)
    if minimum is not None and result < minimum:
        raise ProbeError(f"{field} must be at least {minimum}")
    return result


def _rational(value: object, field: str, *, rate: bool = False) -> Fraction | None:
    if value is None or value == "N/A" or (rate and value in ("0/0", "0/1", "0")):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ProbeError(f"{field} must be a finite number or rational")
    if isinstance(value, float) and not math.isfinite(value):
        raise ProbeError(f"{field} must be finite")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ProbeError(f"{field} must be a finite number or rational") from exc
    if rate and result <= 0:
        raise ProbeError(f"{field} must be positive or unknown")
    return result


def _stream(value: object) -> StreamMetadata:
    item = _object(value, "stream")
    index = _integer(item.get("index"), "stream.index", 0)
    kind = _text(item.get("codec_type"), "stream.codec_type")
    if index is None or kind is None:
        raise ProbeError("Each stream needs an index and codec_type")
    clock = _rational(item.get("time_base"), f"stream {index} time_base")
    if clock is not None and clock <= 0:
        raise ProbeError(f"stream {index} time_base must be positive")
    if kind in ("video", "audio") and clock is None:
        raise ProbeError(f"stream {index} has no usable time_base; source timing is unsupported")
    tags = _object(item.get("tags", {}), "stream.tags")
    sides = item.get("side_data_list", [])
    if not isinstance(sides, list):
        raise ProbeError("stream.side_data_list must be an array")
    rotation = _rational(tags.get("rotate"), "stream.tags.rotate")
    matrix = None
    for side_value in sides:
        side = _object(side_value, "stream side data")
        if side.get("side_data_type") == "Display Matrix":
            rotation = _rational(side.get("rotation"), "display matrix rotation")
            matrix = _text(side.get("displaymatrix"), "display matrix")
    disposition = _object(item.get("disposition", {}), "stream.disposition")
    attached = _integer(disposition.get("attached_pic", 0), "attached_pic", 0)
    duration = _rational(item.get("duration"), "stream.duration")
    if duration is not None and duration < 0:
        raise ProbeError("stream.duration must be nonnegative")
    return StreamMetadata(
        index=index,
        kind=kind,
        codec=_text(item.get("codec_name"), "codec_name"),
        time_base=TimeBase(clock.numerator, clock.denominator) if clock else None,
        start_pts=_integer(item.get("start_pts"), "start_pts"),
        duration_ts=_integer(item.get("duration_ts"), "duration_ts", 0),
        reported_start_seconds=_rational(item.get("start_time"), "stream.start_time"),
        reported_duration_seconds=duration,
        average_frame_rate=_rational(item.get("avg_frame_rate"), "avg_frame_rate", rate=True),
        nominal_frame_rate=_rational(item.get("r_frame_rate"), "r_frame_rate", rate=True),
        width=_integer(item.get("width"), "width", 1),
        height=_integer(item.get("height"), "height", 1),
        rotation_degrees=rotation,
        display_matrix=matrix,
        pixel_format=_text(item.get("pix_fmt"), "pix_fmt"),
        color_range=_text(item.get("color_range"), "color_range"),
        color_space=_text(item.get("color_space"), "color_space"),
        color_transfer=_text(item.get("color_transfer"), "color_transfer"),
        color_primaries=_text(item.get("color_primaries"), "color_primaries"),
        sample_rate=_integer(item.get("sample_rate"), "sample_rate", 1),
        channels=_integer(item.get("channels"), "channels", 1),
        channel_layout=_text(item.get("channel_layout"), "channel_layout"),
        attached_picture=bool(attached),
    )


def parse_probe(payload: str) -> ProbeMetadata:
    """Normalize only reported metadata; never infer frame boundaries from FPS."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON constant: {value}")

    try:
        decoded = json.loads(payload, parse_float=Decimal, parse_constant=reject_constant)
    except (ValueError, RecursionError) as exc:
        raise ProbeError("FFprobe returned malformed JSON") from exc
    data = _object(decoded, "ffprobe output")
    raw_streams = data.get("streams")
    if not isinstance(raw_streams, list) or not raw_streams:
        raise ProbeError("No media streams found; choose a readable video file")
    streams = tuple(_stream(value) for value in raw_streams)
    if len({stream.index for stream in streams}) != len(streams):
        raise ProbeError("FFprobe returned duplicate stream indices")
    videos = [s for s in streams if s.kind == "video" and not s.attached_picture]
    if not videos:
        raise ProbeError("No video stream found (attached cover pictures do not count)")
    info = _object(data.get("format"), "format")
    name = _text(info.get("format_name"), "format_name")
    if name is None:
        raise ProbeError("Missing container format_name")
    version = _text(
        _object(data.get("program_version"), "program_version").get("version"), "ffprobe version"
    )
    if version is None:
        raise ProbeError("Missing FFprobe version; rerun with -show_program_version")
    duration = _rational(info.get("duration"), "format.duration")
    if duration is not None and duration < 0:
        raise ProbeError("format.duration must be nonnegative")
    warnings = ["frame_timestamps_not_scanned"]
    if len(videos) > 1:
        warnings.append("multiple_video_streams_require_explicit_selection_before_editing")
    if any(s.start_pts is None for s in videos):
        warnings.append("video_start_pts_unknown")
    if duration is None:
        warnings.append("container_duration_unknown")
    return ProbeMetadata(
        format_name=name,
        reported_start_seconds=_rational(info.get("start_time"), "format.start_time"),
        reported_duration_seconds=duration,
        streams=streams,
        ffprobe_version=version,
        warnings=tuple(warnings),
    )


def probe_media(source: Path, *, timeout: float = 30) -> ProbeMetadata:
    # Absolute local paths avoid option injection; prohibit network protocols even
    # when a local playlist/container attempts to reference an external URL.
    command = [
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-show_streams",
        "-show_format",
        "-show_program_version",
        "-of",
        "json",
        str(source),
    ]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProbeError("FFprobe not found; install FFmpeg/ffprobe and add it to PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"FFprobe timed out after {timeout:g}s; check the input file") from exc
    except OSError as exc:
        raise ProbeError(f"Could not execute FFprobe: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip()[-2000:]
        raise ProbeError(f"FFprobe could not inspect this video: {detail or 'invalid media'}")
    return parse_probe(result.stdout)
