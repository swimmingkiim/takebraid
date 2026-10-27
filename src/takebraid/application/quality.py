"""Publish source-clock-bound measurements without making exclusion decisions."""

import math
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.identity import file_digest, signature, verify_source
from takebraid.adapters.media.probe import probe_media
from takebraid.adapters.media.quality import (
    MAX_DECODE_BYTES,
    MAX_SAMPLES,
    analysis_tools,
    decode_measurements,
)
from takebraid.adapters.projects import asset_source
from takebraid.adapters.quality import validate_observations
from takebraid.adapters.records import load_asset, load_frame_map
from takebraid.adapters.stages import StageAttempt, cached_output
from takebraid.application.scan import scan_asset
from takebraid.domain.quality import QualitySettings
from takebraid.domain.time import _require_int

RECIPE = "focus-exposure/1"
PIXEL_FORMATS = {
    "gray",
    "yuv420p",
    "yuv422p",
    "yuv444p",
    "yuvj420p",
    "yuvj422p",
    "yuvj444p",
    "rgb24",
    "bgr24",
    "rgba",
    "bgra",
}


def observe_quality(
    asset_path: Path,
    stream_index: int,
    settings: QualitySettings | None = None,
    *,
    timeout: float = 300,
    force: bool = False,
) -> tuple[Path, str]:
    _require_int(stream_index, "stream_index")
    if stream_index < 0:
        raise ValueError("Stream index must be nonnegative")
    settings = QualitySettings() if settings is None else settings
    if not isinstance(settings, QualitySettings):
        raise TypeError("Expected validated quality settings")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be positive and finite")
    asset_path = asset_path.expanduser().resolve(strict=True)
    asset = load_asset(asset_path)
    root, source = asset_source(asset_path, asset)
    digest = asset["source"]["fingerprint"]["digest"]
    before = verify_source(source, digest)
    metadata = probe_media(source)
    stream = next((s for s in metadata.streams if s.index == stream_index), None)
    if stream is None or stream.kind != "video" or stream.attached_picture:
        raise ValueError("Select a video stream, not audio or cover art")
    map_path, _ = scan_asset(asset_path, stream_index, timeout=timeout)
    frame_map = load_frame_map(map_path)
    map_digest = file_digest(map_path)
    if (
        frame_map.asset_id != asset["asset_id"]
        or frame_map.stream_index != stream_index
        or frame_map.time_base != stream.time_base
    ):
        raise ValueError("Analysis map identity/clock mismatch")
    reasons = []
    if not set(metadata.format_name.split(",")) & {"mov", "matroska", "avi", "mpegts", "nut"}:
        reasons.append("unsupported_container_family")
    if frame_map.status != "ready":
        reasons.append("untrusted_source_timing")
    if stream.color_transfer in {"smpte2084", "arib-std-b67"} or stream.color_primaries == "bt2020":
        reasons.append("hdr_or_wide_gamut_not_supported")
    if stream.pixel_format not in PIXEL_FORMATS:
        reasons.append("unsupported_pixel_format")
    if stream.rotation_degrees not in (None, 0) or stream.display_matrix is not None:
        reasons.append("display_transform_not_supported")
    geometry = None
    if not stream.width or not stream.height or min(stream.width, stream.height) < 3:
        reasons.append("unknown_or_small_geometry")
    else:
        geometry = settings.geometry(stream.width, stream.height)
        if len(frame_map.frames) * geometry[0] * geometry[1] > MAX_DECODE_BYTES:
            reasons.append("decoded_byte_budget_exceeded")
        if len(range(0, len(frame_map.frames), settings.every)) > MAX_SAMPLES:
            reasons.append("sample_budget_exceeded")
    tools = analysis_tools()
    inputs = {
        "recipe": RECIPE,
        "takebraid_version": __version__,
        "source_sha256": digest,
        "asset_id": asset["asset_id"],
        "stream_index": stream_index,
        "frame_map_sha256": map_digest,
        "time_base": {
            "numerator": frame_map.time_base.numerator,
            "denominator": frame_map.time_base.denominator,
        },
        "tools": tools,
        "settings": {
            "size": settings.size,
            "every": settings.every,
            "roi": list(settings.roi) if settings.roi else None,
            "timeout": float(timeout),
        },
        "source_geometry": [stream.width, stream.height],
        "pixel_grid": "unrotated-coded-pixels; sample aspect ratio is not normalized",
        "color": {
            "pixel_format": stream.pixel_format,
            "range": stream.color_range,
            "space": stream.color_space,
            "transfer": stream.color_transfer,
            "primaries": stream.color_primaries,
        },
    }
    cached = None if force else cached_output(root, inputs)
    if cached is not None:
        document = validate_observations(cached, inputs, frame_map, settings, geometry, reasons)
        if before != signature(source) or file_digest(map_path) != map_digest:
            raise ValueError("Source/map changed during observation cache verification")
        return cached, document["status"]
    with StageAttempt(root, inputs) as attempt:
        observations = (
            []
            if reasons
            else decode_measurements(
                source,
                frame_map,
                (stream.width, stream.height),
                geometry,
                settings,
                timeout=timeout,
            )
        )
        if before != signature(source) or file_digest(map_path) != map_digest:
            raise ValueError("Source/map changed during quality analysis")
        target = attempt.directory / "quality.json"
        write_new_json(
            target,
            {
                "schema_version": "0.1",
                "inputs": inputs,
                "status": "unknown" if reasons else "observed",
                "reasons": reasons,
                "analysis_geometry": geometry,
                "roi": settings.region(*geometry) if geometry else None,
                "observations": observations,
            },
        )
        document = validate_observations(target, inputs, frame_map, settings, geometry, reasons)
        attempt.complete(target)
        return target, document["status"]
