"""Local model inference with checked source clocks, numerical coverage and cache identity."""

import math
from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.adapters.media.quality import MAX_DECODE_BYTES, decoded_rgb
from takebraid.adapters.models.onnx import LocalOnnxEncoder, load_model_manifest
from takebraid.adapters.records import read_json
from takebraid.adapters.stages import StageAttempt, cached_output
from takebraid.application.analysis import prepare_analysis
from takebraid.domain.embeddings import validate_unit_vector
from takebraid.domain.quality import QualitySettings

RECIPE = "local-onnx-image-embedding/1"
MAX_SAMPLES = 1000


def validate_embeddings(path, context, every, dimensions):
    document = read_json(path, limit=64 * 1024 * 1024)
    if (
        document["inputs"] != context.inputs
        or document["reasons"] != context.reasons
        or document["analysis_geometry"] != list(context.geometry)
    ):
        raise ValueError("Embedding source/model/settings identity mismatch")
    rows = document["observations"]
    schedule = [] if context.reasons else list(range(0, len(context.frame_map.frames), every))
    if not isinstance(rows, list) or len(rows) != len(schedule):
        raise ValueError("Embedding sampling count mismatch")
    unknown = 0
    for row, index in zip(rows, schedule, strict=True):
        if (
            set(row) != {"frame_index", "pts", "status", "reason", "values"}
            or type(row["frame_index"]) is not int
            or row["frame_index"] != index
            or type(row["pts"]) is not int
            or row["pts"] != context.frame_map.frames[index].pts
        ):
            raise ValueError("Embedding source coordinates mismatch")
        if row["status"] == "unknown":
            if row["values"] is not None or row["reason"] not in {
                "nonfinite_model_output",
                "zero_model_output",
            }:
                raise ValueError(
                    "Unknown embeddings need an explicit numerical reason and no vector"
                )
            unknown += 1
        elif row["status"] == "observed" and row["reason"] is None:
            validate_unit_vector(row["values"], dimensions)
        else:
            raise ValueError("Invalid embedding observation status")
    expected = "unknown" if context.reasons else "partial" if unknown else "observed"
    if document["status"] != expected:
        raise ValueError("Embedding numerical coverage/status mismatch")
    return document


def observe_embeddings(
    asset: Path,
    stream_index: int,
    model_manifest: Path,
    *,
    every=25,
    timeout=300,
    inference_timeout=30,
    force=False,
):
    if (
        type(inference_timeout) not in (int, float)
        or not math.isfinite(inference_timeout)
        or not 0 < inference_timeout <= 300
    ):
        raise ValueError("Per-frame cooperative inference deadline must be >0 and <=300 seconds")
    manifest, weights, spec, manifest_hash = load_model_manifest(model_manifest)
    encoder = LocalOnnxEncoder(weights, spec)
    image = spec["input"]
    geometry = (image["width"], image["height"])
    settings = {
        "every": every,
        "timeout": float(timeout),
        "inference_timeout": float(inference_timeout),
        "model_manifest_sha256": manifest_hash,
        "model_spec": spec,
        "runtime": encoder.runtime,
    }
    context = prepare_analysis(
        asset,
        stream_index,
        QualitySettings(size=max(geometry), every=every),
        timeout=timeout,
        recipe=RECIPE,
        semantic_settings=settings,
        max_samples=MAX_SAMPLES,
    )
    context.geometry = geometry
    if len(context.frame_map.frames) * image["width"] * image["height"] * 3 > MAX_DECODE_BYTES:
        context.reasons.append("rgb_decoded_byte_budget_exceeded")

    def stable():
        context.assert_stable()
        if (
            file_digest(manifest) != manifest_hash
            or file_digest(weights) != spec["model"]["sha256"]
        ):
            raise ValueError("Model or manifest changed during embedding inference/cache reuse")

    cached = None if force else cached_output(context.root, context.inputs)
    if cached is not None:
        document = validate_embeddings(cached, context, every, spec["output"]["dimensions"])
        stable()
        return cached, document["status"]
    with StageAttempt(context.root, context.inputs) as attempt:
        rows = []
        if not context.reasons:
            frame_bytes = image["width"] * image["height"] * 3
            with decoded_rgb(
                context.source,
                context.frame_map,
                context.source_geometry,
                geometry,
                timeout=timeout,
            ) as raw:
                for index in range(0, len(context.frame_map.frames), every):
                    raw.seek(index * frame_bytes)
                    values, reason = encoder.encode(raw.read(frame_bytes), inference_timeout)
                    rows.append(
                        {
                            "frame_index": index,
                            "pts": context.frame_map.frames[index].pts,
                            "status": "unknown" if reason else "observed",
                            "reason": reason,
                            "values": values,
                        }
                    )
        stable()
        status = (
            "unknown"
            if context.reasons
            else "partial"
            if any(r["reason"] for r in rows)
            else "observed"
        )
        target = attempt.directory / "embeddings.json"
        write_new_json(
            target,
            {
                "schema_version": "0.1",
                "inputs": context.inputs,
                "status": status,
                "reasons": context.reasons,
                "analysis_geometry": geometry,
                "observations": rows,
            },
        )
        document = validate_embeddings(target, context, every, spec["output"]["dimensions"])
        attempt.complete(target)
        return target, document["status"]
