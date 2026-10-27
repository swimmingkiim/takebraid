"""Interpret validated observations under an explicit calibration-scoped policy."""

import json
from dataclasses import asdict
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import to_json_value, write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.adapters.interpretation import evidence_cells, load_policy
from takebraid.adapters.media.motion import MAX_PAIRS
from takebraid.adapters.motion import validate_motion
from takebraid.adapters.quality import validate_observations
from takebraid.adapters.records import read_json
from takebraid.adapters.stages import StageAttempt, cached_output, completed_artifact
from takebraid.application.analysis import prepare_analysis
from takebraid.domain.motion import MotionSettings
from takebraid.domain.quality import QualitySettings
from takebraid.quality.motion import grid_points
from takebraid.quality.temporal import interpret_cells

RECIPE = "temporal-candidates/1"


def validated_observation(asset: Path, observation: Path, kind: str):
    document = read_json(observation)
    inputs = document["inputs"]
    raw = inputs["settings"]
    expected_keys = (
        {"size", "every", "roi", "timeout"}
        if kind == "quality"
        else {"size", "every", "radius", "background", "timeout"}
    )
    recipe = "focus-exposure/1" if kind == "quality" else "background-translation/1"
    if inputs["recipe"] != recipe or set(raw) != expected_keys:
        raise ValueError("Policy requires a supported observation recipe/settings")
    if kind == "quality":
        settings = QualitySettings(
            raw["size"], raw["every"], tuple(raw["roi"]) if raw["roi"] is not None else None
        )
        grid, limit = settings, 10000
    else:
        settings = MotionSettings(
            raw["size"],
            raw["every"],
            raw["radius"],
            tuple(raw["background"]) if raw["background"] is not None else None,
        )
        grid, limit = settings.grid(), MAX_PAIRS + 1
    context = prepare_analysis(
        asset,
        inputs["stream_index"],
        grid,
        timeout=raw["timeout"],
        recipe=recipe,
        semantic_settings=raw,
        max_samples=limit,
    )
    if inputs != context.inputs:
        raise ValueError("Observation source/map/tool revisions differ; regenerate observations")
    if completed_artifact(context.root, observation) != inputs:
        raise ValueError("Observation inputs differ from terminal receipt")
    reasons, geometry = list(context.reasons), context.geometry
    if kind == "quality":
        document = validate_observations(
            observation, inputs, context.frame_map, settings, geometry, reasons
        )
    else:
        if len(range(0, len(context.frame_map.frames), settings.every)) < 2:
            reasons.append("insufficient_sampled_frames")
        if geometry and not grid_points(grid.region(*geometry), settings.radius):
            reasons.append("insufficient_analysis_region")
        document = validate_motion(
            observation, inputs, context.frame_map, settings, geometry, reasons
        )
    context.assert_stable()
    return context, document


def interpret_observation(
    asset_path: Path,
    observation_path: Path,
    policy_path: Path,
    *,
    force: bool = False,
) -> tuple[Path, str]:
    observation_path = observation_path.expanduser().resolve(strict=True)
    policy_path = policy_path.expanduser().resolve(strict=True)
    policy_digest = file_digest(policy_path)
    policy = load_policy(policy_path)
    observation_digest = file_digest(observation_path)
    context, document = validated_observation(asset_path, observation_path, policy.source_kind)
    frame_map = context.frame_map
    inputs = {
        "recipe": RECIPE,
        "takebraid_version": __version__,
        "observation_sha256": observation_digest,
        "observation_inputs": context.inputs,
        "policy_sha256": policy_digest,
        "policy": to_json_value(asdict(policy)),
    }

    def stable():
        context.assert_stable()
        if (
            file_digest(policy_path) != policy_digest
            or file_digest(observation_path) != observation_digest
        ):
            raise ValueError("Policy/observation changed during interpretation")

    def expected_document():
        return interpretation_document(inputs, document, frame_map, policy)

    cached = None if force else cached_output(context.root, inputs)
    if cached is not None:
        expected, status = expected_document()
        if json.dumps(read_json(cached), sort_keys=True) != json.dumps(expected, sort_keys=True):
            raise ValueError("Cached interpretation differs from recomputed evidence")
        stable()
        return cached, status
    with StageAttempt(context.root, inputs) as attempt:
        expected, status = expected_document()
        target = attempt.directory / "interpretation.json"
        write_new_json(target, expected)
        stable()
        if read_json(target) != expected:
            raise ValueError("Interpretation publication mismatch")
        attempt.complete(target)
        return target, status


def interpretation_document(inputs, document, frame_map, policy):
    if frame_map.status == "ready":
        result = interpret_cells(
            evidence_cells(document, frame_map, policy), frame_map.time_base, policy
        )
        reasons = []
    else:
        result = {"status": "unknown", "cells": [], "candidates": [], "short_runs": []}
        reasons = ["untrusted_source_timing"]
    expected = to_json_value(
        {
            "schema_version": "0.1",
            "artifact_kind": "interpretation",
            "decision_effect": "none",
            "observation_reasons": document["reasons"],
            "inputs": inputs,
            "reasons": reasons,
            "interpretation": result,
        }
    )
    return expected, result["status"]
