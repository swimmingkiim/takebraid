"""Versioned artifact readers. Saved summaries never replace domain validation."""

import json
import math
import re
from dataclasses import fields
from fractions import Fraction
from pathlib import Path, PurePosixPath, PureWindowsPath

from takebraid.domain.frames import FrameMap, FrameObservation
from takebraid.domain.metadata import StreamMetadata
from takebraid.domain.time import TimeBase, _require_int


class RecordError(ValueError):
    """Unsupported, malformed or inconsistent persisted data."""


def absolute_locator(value: object) -> bool:
    # A moved project must remain readable on another OS before relinking.
    return isinstance(value, str) and (
        PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
    )


def read_json(path: Path, *, limit: int = 128 * 1024 * 1024) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RecordError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise RecordError(f"Nonfinite JSON constant: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise RecordError("Nonfinite JSON number")
        return number

    try:
        if path.stat().st_size > limit:
            raise RecordError(f"Artifact exceeds {limit} byte limit: {path}")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
            parse_float=finite_float,
        )
        if not isinstance(value, dict) or value.get("schema_version") != "0.1":
            raise RecordError("Unsupported artifact schema; expected version 0.1")
        return value
    except (OSError, ValueError, RecursionError) as exc:
        raise RecordError(f"Cannot read artifact {path}: {exc}") from exc


def content_identity(document: dict) -> str:
    try:
        digest = document["source"]["fingerprint"]["digest"]
        if (
            document["source"]["fingerprint"]["algorithm"] != "sha256"
            or not isinstance(digest, str)
            or not re.fullmatch("[0-9a-f]{64}", digest)
            or document["asset_id"] != f"sha256-{digest}"
        ):
            raise RecordError("Invalid asset content identity")
        return digest
    except (KeyError, TypeError) as exc:
        raise RecordError("Missing asset content identity") from exc


def _fraction(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise RecordError("Expected numerator/denominator rational")
    _require_int(value["numerator"], "numerator")
    _require_int(value["denominator"], "denominator")
    if value["denominator"] <= 0:
        raise RecordError("Rational denominator must be positive")
    return Fraction(value["numerator"], value["denominator"])


def _clock(value) -> TimeBase:
    ratio = _fraction(value)
    if ratio is None or ratio <= 0:
        raise RecordError("Source clock must be positive")
    return TimeBase(ratio.numerator, ratio.denominator)


def load_asset(path: Path) -> dict:
    """Validate persisted normalized metadata; source existence is checked separately."""
    document = read_json(path, limit=2 * 1024 * 1024)
    try:
        content_identity(document)
        source = document["source"]
        locator = source["locator"]
        if not absolute_locator(locator):
            raise RecordError("Source locator must be an absolute local path")
        for name in ("size_bytes", "mtime_ns"):
            _require_int(source[name], name)
        if source["size_bytes"] < 0:
            raise RecordError("Source size must be nonnegative")
        metadata = document["metadata"]
        for name in ("format_name", "ffprobe_version"):
            if not isinstance(metadata[name], str) or not metadata[name]:
                raise RecordError(f"Missing metadata {name}")
        for name in ("reported_start_seconds", "reported_duration_seconds"):
            ratio = _fraction(metadata[name])
            if name == "reported_duration_seconds" and ratio is not None and ratio < 0:
                raise RecordError("Duration must be nonnegative")
        if not isinstance(metadata["warnings"], list) or not all(
            isinstance(warning, str) for warning in metadata["warnings"]
        ):
            raise RecordError("Warnings must be strings")
        streams = []
        rational_names = {
            "reported_start_seconds",
            "reported_duration_seconds",
            "average_frame_rate",
            "nominal_frame_rate",
            "rotation_degrees",
        }
        integer_names = {
            "index",
            "start_pts",
            "duration_ts",
            "width",
            "height",
            "sample_rate",
            "channels",
        }
        if not isinstance(metadata["streams"], list):
            raise RecordError("Streams must be an array")
        for stream in metadata["streams"]:
            normalized = {}
            for field in fields(StreamMetadata):
                name = field.name
                value = stream[name]
                if name == "time_base":
                    value = _clock(value) if value is not None else None
                elif name in rational_names:
                    value = _fraction(value)
                    if value is not None:
                        if name in {"average_frame_rate", "nominal_frame_rate"} and value <= 0:
                            raise RecordError("Frame rate must be positive or null")
                        if name == "reported_duration_seconds" and value < 0:
                            raise RecordError("Duration must be nonnegative")
                elif name in integer_names:
                    if value is not None:
                        _require_int(value, name)
                        if name in {"index", "duration_ts"} and value < 0:
                            raise RecordError(f"{name} must be nonnegative")
                        if name in {"width", "height", "sample_rate", "channels"} and value <= 0:
                            raise RecordError(f"{name} must be positive")
                elif name == "attached_picture":
                    if not isinstance(value, bool):
                        raise RecordError("attached_picture must be boolean")
                elif value is not None and (not isinstance(value, str) or not value):
                    raise RecordError(f"{name} must be a nonempty string or null")
                normalized[name] = value
            item = StreamMetadata(**normalized)
            if item.index is None or item.kind is None:
                raise RecordError("Stream identity is required")
            if item.kind in {"video", "audio"} and item.time_base is None:
                raise RecordError("Audio/video clock is required")
            streams.append(item)
        if len({s.index for s in streams}) != len(streams):
            raise RecordError("Duplicate stream indices")
        if not any(s.kind == "video" and not s.attached_picture for s in streams):
            raise RecordError("Asset needs a video stream")
        # Return original additive fields/annotations after validating consumed data.
        return document
    except (KeyError, TypeError, ValueError) as exc:
        raise RecordError(f"Invalid asset record: {exc}") from exc


def load_frame_map(path: Path) -> FrameMap:
    document = read_json(path)
    try:
        raw = document["frame_map"]
        if not isinstance(raw["frames"], list):
            raise RecordError("Frames must be an array")
        result = FrameMap(
            raw["asset_id"],
            raw["stream_index"],
            _clock(raw["time_base"]),
            tuple(FrameObservation(**frame) for frame in raw["frames"]),
        )
        if not re.fullmatch(r"sha256-[0-9a-f]{64}", result.asset_id):
            raise RecordError("Invalid frame-map asset identity")
        expected_issues = [
            {"code": issue.code, "frame_index": issue.frame_index} for issue in result.issues
        ]
        if (
            document["status"] != result.status
            or document["issues"] != expected_issues
            or document["presentation_end_pts"] != result.presentation_end_pts
            or document["cadence"] != result.cadence
        ):
            raise RecordError("Frame-map summary disagrees with decoded evidence")
        if document["provenance"]["source_sha256"] != result.asset_id.removeprefix("sha256-"):
            raise RecordError("Frame-map provenance does not match asset identity")
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise RecordError(f"Invalid frame map: {exc}") from exc
