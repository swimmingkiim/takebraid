"""Validate saved observation identity, sampling schedule and metric invariants."""

from dataclasses import fields
from pathlib import Path

from takebraid.adapters.records import _fraction, read_json
from takebraid.domain.frames import FrameMap
from takebraid.domain.quality import QualityMetrics, QualitySettings


def validate_observations(
    path: Path,
    inputs: dict,
    frame_map: FrameMap,
    settings: QualitySettings,
    geometry: tuple[int, int] | None,
    reasons: list[str],
) -> dict:
    document = read_json(path)
    expected_status = "unknown" if reasons else "observed"
    if (
        document["inputs"] != inputs
        or document["status"] != expected_status
        or document["reasons"] != reasons
        or document["analysis_geometry"] != (list(geometry) if geometry else None)
        or document["roi"] != (list(settings.region(*geometry)) if geometry else None)
    ):
        raise ValueError("Observation identity/settings/status mismatch; use --force")
    observations = document["observations"]
    schedule = [] if reasons else list(range(0, len(frame_map.frames), settings.every))
    if not isinstance(observations, list) or len(observations) != len(schedule):
        raise ValueError("Observation sampling count mismatch")
    for row, index in zip(observations, schedule, strict=True):
        if (
            type(row["frame_index"]) is not int
            or row["frame_index"] != index
            or type(row["pts"]) is not int
            or row["pts"] != frame_map.frames[index].pts
        ):
            raise ValueError("Observation source coordinates mismatch")
        raw = row["metrics"]
        if set(raw) != {field.name for field in fields(QualityMetrics)}:
            raise ValueError("Unexpected metric fields")
        QualityMetrics(**{key: _fraction(value) for key, value in raw.items()})
    return document
