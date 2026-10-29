"""Cache exact spatial descriptors and propose review-only cross-source visual matches."""

from fractions import Fraction
from pathlib import Path

from takebraid.adapters.artifacts import to_json_value, write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.adapters.records import _fraction, read_json
from takebraid.adapters.stages import StageAttempt, cached_output, completed_artifact
from takebraid.adapters.visual import MAX_SAMPLES, decode_descriptors, validate_descriptors
from takebraid.application.analysis import prepare_analysis
from takebraid.domain.quality import QualitySettings
from takebraid.domain.visual import GRID, GridDescriptor, match_series

RECIPE = "gray-spatial-grid/1"
COMPARE_RECIPE = "spatial-match-proposals/1"


def visual_context(asset, stream_index, size, every, timeout):
    settings = QualitySettings(size=size, every=every)
    context = prepare_analysis(
        asset,
        stream_index,
        settings,
        timeout=timeout,
        recipe=RECIPE,
        semantic_settings={"size": size, "every": every, "grid": GRID, "timeout": float(timeout)},
        max_samples=MAX_SAMPLES,
    )
    if context.geometry and min(context.geometry) < GRID:
        context.reasons.append("descriptor_grid_too_small")
    return context


def observe_visual(asset: Path, stream_index: int, *, size=64, every=25, timeout=300, force=False):
    context = visual_context(asset, stream_index, size, every, timeout)
    cached = None if force else cached_output(context.root, context.inputs)
    if cached is not None:
        document = validate_descriptors(cached, context, every)
        context.assert_stable()
        return cached, document["status"]
    with StageAttempt(context.root, context.inputs) as attempt:
        rows = [] if context.reasons else decode_descriptors(context, every)
        context.assert_stable()
        target = attempt.directory / "visual.json"
        write_new_json(
            target,
            {
                "schema_version": "0.1",
                "inputs": context.inputs,
                "status": "unknown" if context.reasons else "observed",
                "reasons": context.reasons,
                "analysis_geometry": context.geometry,
                "observations": rows,
            },
        )
        document = validate_descriptors(target, context, every)
        attempt.complete(target)
        return target, document["status"]


def compare_visual(
    sources: list[tuple[Path, Path]],
    output: Path,
    *,
    max_distance: Fraction,
    min_variance: Fraction,
    limit=20,
    force=False,
):
    if not 2 <= len(sources) <= 10:
        raise ValueError("Compare 2..10 distinct source assets")
    prepared = []
    total_samples = 0
    for asset, descriptor in sources:
        descriptor = descriptor.expanduser().resolve(strict=True)
        digest = file_digest(descriptor)
        raw = read_json(descriptor, limit=16 * 1024 * 1024)
        settings = raw["inputs"]["settings"]
        if (
            set(settings) != {"size", "every", "grid", "timeout"}
            or settings["grid"] != GRID
            or raw["inputs"]["recipe"] != RECIPE
        ):
            raise ValueError("Unsupported visual descriptor recipe/grid")
        context = visual_context(
            asset,
            raw["inputs"]["stream_index"],
            settings["size"],
            settings["every"],
            settings["timeout"],
        )
        if completed_artifact(context.root, descriptor) != context.inputs:
            raise ValueError("Descriptor inputs differ from completed receipt")
        document = validate_descriptors(descriptor, context, settings["every"])
        if digest != file_digest(descriptor):
            raise ValueError("Descriptor changed while loading")
        total_samples += len(document["observations"])
        if total_samples > 2000:
            raise ValueError("Comparison exceeds 2000 total samples")
        prepared.append((context, document, descriptor, digest))
    prepared.sort(key=lambda row: row[0].frame_map.asset_id)
    series = []
    for context, document, _, _ in prepared:
        rows = [
            {
                "point": {
                    "frame_index": row["frame_index"],
                    "pts": row["pts"],
                    "stream_index": context.frame_map.stream_index,
                    "time_base": context.inputs["time_base"],
                },
                "descriptor": GridDescriptor(tuple(_fraction(v) for v in row["values"])),
            }
            for row in document["observations"]
        ]
        series.append(
            {
                "asset_id": context.frame_map.asset_id,
                "aspect": Fraction(*context.source_geometry)
                if all(type(v) is int and v > 0 for v in context.source_geometry)
                else None,
                "rows": rows,
            }
        )
    # Domain validation and pair budgets run even on cache reuse.
    result = match_series(series, max_distance, min_variance, limit)
    inputs = to_json_value(
        {
            "recipe": COMPARE_RECIPE,
            "observations": [
                {"inputs": c.inputs, "sha256": digest} for c, _, _, digest in prepared
            ],
            "max_distance": max_distance,
            "min_variance": min_variance,
            "limit": limit,
        }
    )
    report = to_json_value(
        {
            "schema_version": "0.1",
            "inputs": inputs,
            "scope": "sampled_grayscale_spatial_match_candidates",
            "semantic_equivalence_validated": False,
            "automatic_exclusion_validated": False,
            "input_status": [
                {"asset_id": c.frame_map.asset_id, "status": d["status"], "reasons": d["reasons"]}
                for c, d, _, _ in prepared
            ],
            **result,
        }
    )

    def stable():
        for context, _, descriptor, digest in prepared:
            context.assert_stable()
            if file_digest(descriptor) != digest:
                raise ValueError("Descriptor changed during comparison")

    cached = None if force else cached_output(output, inputs)
    if cached is not None:
        if read_json(cached) != report:
            raise ValueError(
                "Visual comparison content differs from recomputed proposals; use --force"
            )
        stable()
        return cached
    with StageAttempt(output, inputs) as attempt:
        stable()
        target = attempt.directory / "matches.json"
        write_new_json(target, report)
        attempt.complete(target)
        return target
