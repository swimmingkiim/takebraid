"""Preserved translation candidates with uncertainty; never automatic exclusions."""

from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.media.motion import MAX_PAIRS, decode_motion
from takebraid.adapters.motion import motion_status, validate_motion
from takebraid.adapters.stages import StageAttempt, cached_output
from takebraid.application.analysis import prepare_analysis
from takebraid.domain.motion import MotionSettings
from takebraid.quality.motion import grid_points, path_evidence

RECIPE = "background-translation/1"


def observe_motion(
    asset_path: Path,
    stream_index: int,
    settings: MotionSettings | None = None,
    *,
    timeout: float = 300,
    force: bool = False,
) -> tuple[Path, str]:
    settings = MotionSettings() if settings is None else settings
    if not isinstance(settings, MotionSettings):
        raise TypeError("Expected validated motion settings")
    context = prepare_analysis(
        asset_path,
        stream_index,
        settings.grid(),
        timeout=timeout,
        recipe=RECIPE,
        semantic_settings={
            "size": settings.size,
            "every": settings.every,
            "radius": settings.radius,
            "background": list(settings.background) if settings.background else None,
            "timeout": float(timeout),
        },
        max_samples=MAX_PAIRS + 1,
    )
    geometry, reasons = context.geometry, list(context.reasons)
    if len(range(0, len(context.frame_map.frames), settings.every)) < 2:
        reasons.append("insufficient_sampled_frames")
    region = settings.grid().region(*geometry) if geometry else None
    if region and not grid_points(region, settings.radius):
        reasons.append("insufficient_analysis_region")
    inputs = context.inputs
    cached = None if force else cached_output(context.root, inputs)
    if cached is not None:
        document = validate_motion(cached, inputs, context.frame_map, settings, geometry, reasons)
        context.assert_stable()
        return cached, document["status"]
    with StageAttempt(context.root, inputs) as attempt:
        pairs = (
            []
            if reasons
            else decode_motion(
                context.source,
                context.frame_map,
                context.source_geometry,
                geometry,
                settings,
                timeout=timeout,
            )
        )
        context.assert_stable()
        target = attempt.directory / "motion.json"
        write_new_json(
            target,
            {
                "schema_version": "0.1",
                "inputs": inputs,
                "reasons": reasons,
                "status": motion_status(pairs, reasons),
                "analysis_geometry": geometry,
                "region": region,
                "model_role": "declared_background_translation"
                if settings.background
                else "dominant_image_translation",
                "pairs": pairs,
                "path": path_evidence(pairs, context.frame_map.time_base.seconds(1)),
            },
        )
        document = validate_motion(target, inputs, context.frame_map, settings, geometry, reasons)
        attempt.complete(target)
        return target, document["status"]
