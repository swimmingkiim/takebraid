"""Recompute motion consensus, sampling and path summaries before cache reuse."""

import json
from pathlib import Path

from takebraid.adapters.artifacts import to_json_value
from takebraid.adapters.records import read_json
from takebraid.domain.frames import FrameMap
from takebraid.domain.motion import MotionSettings
from takebraid.quality.motion import MAX_SAD, grid_points, path_evidence, summarize_tracks

REJECTION_CODES = {
    "low_texture",
    "photometric_mismatch",
    "ambiguous",
    "search_boundary",
    "forward_backward",
}


def motion_status(pairs: list[dict], reasons: list[str]) -> str:
    if reasons or not pairs or not any(p["status"] == "observed" for p in pairs):
        return "unknown"
    return "partial" if any(p["status"] == "unknown" for p in pairs) else "observed"


def validate_motion(
    path: Path,
    inputs: dict,
    frame_map: FrameMap,
    settings: MotionSettings,
    geometry: tuple[int, int] | None,
    reasons: list[str],
) -> dict:
    document = read_json(path)
    region = settings.grid().region(*geometry) if geometry else None
    role = (
        "declared_background_translation" if settings.background else "dominant_image_translation"
    )
    if (
        document["inputs"] != inputs
        or document["reasons"] != reasons
        or document["analysis_geometry"] != (list(geometry) if geometry else None)
        or document["region"] != (list(region) if region else None)
        or document["model_role"] != role
    ):
        raise ValueError("Motion identity/settings/geometry mismatch")
    schedule = list(range(0, len(frame_map.frames), settings.every))
    expected = [] if reasons else list(zip(schedule, schedule[1:], strict=False))
    pairs = document["pairs"]
    if not isinstance(pairs, list) or len(pairs) != len(expected):
        raise ValueError("Motion pair schedule mismatch")
    for pair, (first, second) in zip(pairs, expected, strict=True):
        coordinates = {
            "from_frame": first,
            "to_frame": second,
            "from_pts": frame_map.frames[first].pts,
            "to_pts": frame_map.frames[second].pts,
        }
        if any(
            type(pair[key]) is not int or pair[key] != value for key, value in coordinates.items()
        ):
            raise ValueError("Motion source coordinates mismatch")
        points = set(grid_points(region, settings.radius))
        if type(pair["grid_points"]) is not int or pair["grid_points"] != len(points):
            raise ValueError("Motion grid evidence mismatch")
        seen = set()
        tracks = pair["tracks"]
        if not isinstance(tracks, list):
            raise ValueError("Motion tracks must be an array")
        for track in tracks:
            if set(track) != {"x", "y", "dx", "dy", "sad"} or any(
                type(v) is not int for v in track.values()
            ):
                raise ValueError("Invalid motion track fields")
            point = (track["x"], track["y"])
            if (
                point not in points
                or point in seen
                or not 0 <= track["sad"] <= MAX_SAD
                or abs(track["dx"]) >= settings.radius
                or abs(track["dy"]) >= settings.radius
            ):
                raise ValueError("Invalid motion track coordinates/cost")
            seen.add(point)
        rejected = pair["rejected"]
        if (
            not isinstance(rejected, dict)
            or set(rejected) - REJECTION_CODES
            or any(type(v) is not int or v <= 0 for v in rejected.values())
            or len(tracks) + sum(rejected.values()) != len(points)
        ):
            raise ValueError("Motion rejected-track accounting mismatch")
        summary = to_json_value(summarize_tracks(tracks, region))
        for key, value in summary.items():
            if json.dumps(pair[key], sort_keys=True) != json.dumps(value, sort_keys=True):
                raise ValueError("Motion consensus summary does not match saved evidence")
    expected_path = to_json_value(path_evidence(pairs, frame_map.time_base.seconds(1)))
    if json.dumps(document["path"], sort_keys=True) != json.dumps(
        expected_path, sort_keys=True
    ) or document["status"] != motion_status(pairs, reasons):
        raise ValueError("Motion path/status summary mismatch")
    return document
