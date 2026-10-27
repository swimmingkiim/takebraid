"""Publish source-clock-bound measurements without making exclusion decisions."""

from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.media.quality import decode_measurements
from takebraid.adapters.quality import validate_observations
from takebraid.adapters.stages import StageAttempt, cached_output
from takebraid.application.analysis import prepare_analysis
from takebraid.domain.quality import QualitySettings

RECIPE = "focus-exposure/1"


def observe_quality(
    asset_path: Path,
    stream_index: int,
    settings: QualitySettings | None = None,
    *,
    timeout: float = 300,
    force: bool = False,
) -> tuple[Path, str]:
    settings = QualitySettings() if settings is None else settings
    if not isinstance(settings, QualitySettings):
        raise TypeError("Expected validated quality settings")
    context = prepare_analysis(
        asset_path,
        stream_index,
        settings,
        timeout=timeout,
        recipe=RECIPE,
        semantic_settings={
            "size": settings.size,
            "every": settings.every,
            "roi": list(settings.roi) if settings.roi else None,
            "timeout": float(timeout),
        },
    )
    inputs, frame_map = context.inputs, context.frame_map
    geometry, reasons = context.geometry, context.reasons
    cached = None if force else cached_output(context.root, inputs)
    if cached is not None:
        document = validate_observations(cached, inputs, frame_map, settings, geometry, reasons)
        context.assert_stable()
        return cached, document["status"]
    with StageAttempt(context.root, inputs) as attempt:
        observations = (
            []
            if reasons
            else decode_measurements(
                context.source,
                frame_map,
                context.source_geometry,
                geometry,
                settings,
                timeout=timeout,
            )
        )
        context.assert_stable()
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
