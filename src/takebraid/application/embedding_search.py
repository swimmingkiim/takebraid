"""Runtime-free replay and cosine search over checked, compatible embedding observations."""

import platform
from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.records import read_json
from takebraid.adapters.stages import StageAttempt, cached_output, stage_key
from takebraid.application.embeddings import RECIPE as EMBEDDING_RECIPE
from takebraid.application.embeddings import load_saved_embeddings
from takebraid.domain.embeddings import search_series

RECIPE = "saved-embedding-cosine-search/1"


def embedding_space(inputs):
    settings = inputs["settings"]
    return {
        "recipe": EMBEDDING_RECIPE,
        "model_spec": settings["model_spec"],
        "runtime": settings["runtime"],
        "media_tools": inputs["tools"],
    }


def search_embeddings(
    sources: list[tuple[Path, Path]], output: Path, *, min_cosine: float, limit=20, force=False
):
    if not 2 <= len(sources) <= 10:
        raise ValueError("Search requires 2..10 distinct source assets")
    prepared, coordinates, samples = [], 0, 0
    for asset, artifact in sources:
        context, document, digest, stable = load_saved_embeddings(asset, artifact)
        count = len(document["observations"])
        samples += count
        coordinates += count * document["inputs"]["settings"]["model_spec"]["output"]["dimensions"]
        if samples > 2000 or coordinates > 2000000:
            raise ValueError("Search exceeds 2000 samples or 2000000 vector coordinates")
        prepared.append((context, document, digest, stable))
    prepared.sort(key=lambda row: row[0].frame_map.asset_id)
    space = embedding_space(prepared[0][1]["inputs"])
    if any(embedding_space(d["inputs"]) != space for _, d, _, _ in prepared):
        raise ValueError(
            "Incompatible embedding spaces: model/preprocessing/runtime/media tools differ"
        )
    series = [
        {
            "asset_id": c.frame_map.asset_id,
            "rows": [
                {
                    "point": {
                        "frame_index": r["frame_index"],
                        "pts": r["pts"],
                        "stream_index": c.frame_map.stream_index,
                        "time_base": c.inputs["time_base"],
                    },
                    "values": r["values"],
                }
                for r in d["observations"]
            ],
        }
        for c, d, _, _ in prepared
    ]
    result = search_series(series, space["model_spec"]["output"]["dimensions"], min_cosine, limit)
    inputs = {
        "recipe": RECIPE,
        "embedding_space_sha256": stage_key(space),
        "math_environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "observations": [{"inputs": d["inputs"], "sha256": digest} for _, d, digest, _ in prepared],
        "min_cosine": min_cosine,
        "limit": limit,
    }
    report = {
        "schema_version": "0.1",
        "inputs": inputs,
        "scope": "sampled_embedding_cosine_review_candidates",
        "semantic_accuracy_validated": False,
        "automatic_exclusion_validated": False,
        "source_coverage": [
            {"asset_id": c.frame_map.asset_id, "status": d["status"], "reasons": d["reasons"]}
            for c, d, _, _ in prepared
        ],
        **result,
    }

    def stable_all():
        for _, _, _, stable in prepared:
            stable()

    cached = None if force else cached_output(output, inputs)
    if cached is not None:
        if read_json(cached) != report:
            raise ValueError("Saved search differs from recomputed candidates; use --force")
        stable_all()
        return cached
    with StageAttempt(output, inputs) as attempt:
        stable_all()
        target = attempt.directory / "embedding-matches.json"
        write_new_json(target, report)
        attempt.complete(target)
        return target
