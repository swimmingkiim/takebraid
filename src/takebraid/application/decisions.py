"""Immutable user decision snapshots, checked provenance and bound manual previews."""

import json
import re
import uuid
from dataclasses import asdict, fields
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import to_json_value, write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.adapters.projects import project_path
from takebraid.adapters.records import _fraction, read_json
from takebraid.adapters.stages import completed_artifact
from takebraid.application.interpretation import interpretation_document, validated_observation
from takebraid.application.preview import create_plan
from takebraid.domain.decisions import (
    MAX_OVERRIDES,
    DecisionOverride,
    included_cuts,
    resolve_decisions,
)
from takebraid.domain.interpretation import TemporalPolicy
from takebraid.domain.time import SourceRange

RECIPE = "reversible-decisions/1"


def _same(a, b):
    return json.dumps(to_json_value(a), sort_keys=True) == json.dumps(
        to_json_value(b), sort_keys=True
    )


def _interpretation(asset, observation, interpretation):
    observation = observation.expanduser().resolve(strict=True)
    interpretation = interpretation.expanduser().resolve(strict=True)
    digest = file_digest(interpretation)
    observation_digest = file_digest(observation)
    document = read_json(interpretation)
    inputs = document["inputs"]
    raw = inputs["policy"]
    if set(raw) != {f.name for f in fields(TemporalPolicy)}:
        raise ValueError("Invalid saved temporal policy")
    policy = TemporalPolicy(
        **{
            key: value if key in {"name", "calibration", "metric"} else _fraction(value)
            for key, value in raw.items()
        }
    )
    context, observations = validated_observation(asset, observation, policy.source_kind)
    expected_inputs = {
        "recipe": "temporal-candidates/1",
        "takebraid_version": __version__,
        "observation_sha256": observation_digest,
        "observation_inputs": context.inputs,
        "policy_sha256": inputs["policy_sha256"],
        "policy": raw,
    }
    if not isinstance(inputs["policy_sha256"], str) or not re.fullmatch(
        r"[a-f0-9]{64}", inputs["policy_sha256"]
    ):
        raise ValueError("Invalid interpretation policy identity")
    if not _same(inputs, expected_inputs) or not _same(
        completed_artifact(context.root, interpretation), inputs
    ):
        raise ValueError("Interpretation inputs/receipt mismatch")
    expected, _ = interpretation_document(inputs, observations, context.frame_map, policy)
    if not _same(document, expected):
        raise ValueError("Interpretation differs from recomputed evidence")
    context.frame_map.boundaries()  # Unknown timing cannot define an editable partition.

    def stable():
        context.assert_stable()
        if file_digest(interpretation) != digest or file_digest(observation) != observation_digest:
            raise ValueError("Interpretation/observation changed during decision operation")

    stable()
    return context, document, digest, observation_digest, stable


def _publish(
    context,
    asset,
    interpretation,
    observation,
    interpretation_digest,
    observation_digest,
    overrides,
    parent,
    evidence,
    stable,
):
    identity = uuid.uuid4().hex
    intervals = resolve_decisions(context.frame_map, evidence, overrides)
    document = {
        "schema_version": "0.1",
        "artifact_kind": "decision",
        "recipe": RECIPE,
        "decision_id": identity,
        "asset_metadata_path": asset.expanduser()
        .resolve(strict=True)
        .relative_to(context.root)
        .as_posix(),
        "asset_id": context.frame_map.asset_id,
        "stream_index": context.frame_map.stream_index,
        "time_base": context.frame_map.time_base,
        "interpretation": {
            "path": interpretation.relative_to(context.root).as_posix(),
            "sha256": interpretation_digest,
        },
        "observation": {
            "path": observation.relative_to(context.root).as_posix(),
            "sha256": observation_digest,
        },
        "parent": parent,
        "overrides": [asdict(o) for o in overrides],
        "intervals": intervals,
    }
    stable()
    path = project_path(context.root, f"decisions/{identity}/decision.json")
    write_new_json(path, document)
    return path


def create_decisions(asset: Path, observation: Path, interpretation: Path) -> Path:
    observation = observation.expanduser().resolve(strict=True)
    interpretation = interpretation.expanduser().resolve(strict=True)
    context, document, ih, oh, stable = _interpretation(asset, observation, interpretation)
    return _publish(
        context,
        asset,
        interpretation,
        observation,
        ih,
        oh,
        (),
        None,
        document["interpretation"],
        stable,
    )


def load_decisions(asset: Path, path: Path):
    path = path.expanduser().resolve(strict=True)
    leaf_digest = file_digest(path)
    leaf = read_json(path)
    # Resolve dependencies relative to the registered asset project.
    from takebraid.adapters.projects import asset_source
    from takebraid.adapters.records import load_asset

    actual_asset = asset.expanduser().resolve(strict=True)
    root, _ = asset_source(actual_asset, load_asset(actual_asset))
    interpretation = project_path(root, leaf["interpretation"]["path"])
    observation = project_path(root, leaf["observation"]["path"])
    context, document, ih, oh, base_stable = _interpretation(asset, observation, interpretation)
    references = {
        "asset_metadata_path": actual_asset.relative_to(root).as_posix(),
        "asset_id": context.frame_map.asset_id,
        "stream_index": context.frame_map.stream_index,
        "time_base": to_json_value(context.frame_map.time_base),
        "interpretation": {"path": interpretation.relative_to(root).as_posix(), "sha256": ih},
        "observation": {"path": observation.relative_to(root).as_posix(), "sha256": oh},
    }
    current_path, current = path, leaf
    current_digest = leaf_digest
    snapshots = []
    for _ in range(MAX_OVERRIDES + 1):
        identity = current["decision_id"]
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[a-f0-9]{32}", identity)
            or current_path != root / "decisions" / identity / "decision.json"
            or current["artifact_kind"] != "decision"
            or current["recipe"] != RECIPE
            or any(not _same(current[key], value) for key, value in references.items())
        ):
            raise ValueError("Decision identity/source/provenance mismatch")
        if not isinstance(current["overrides"], list) or len(current["overrides"]) > MAX_OVERRIDES:
            raise ValueError("Invalid decision history")
        snapshots.append((current_path, current_digest))
        parent = current["parent"]
        if parent is None:
            if current["overrides"]:
                raise ValueError("Initial decision snapshot cannot contain overrides")
            break
        parent_path = project_path(root, parent["path"])
        if file_digest(parent_path) != parent["sha256"]:
            raise ValueError("Decision parent checksum changed")
        previous = read_json(parent_path)
        if not current["overrides"] or not _same(previous["overrides"], current["overrides"][:-1]):
            raise ValueError("Decision parent/override history mismatch")
        current_path, current = parent_path, previous
        current_digest = parent["sha256"]
    else:
        raise ValueError("Decision history exceeds 100 overrides or contains a cycle")
    overrides = tuple(DecisionOverride(**row) for row in leaf["overrides"])
    expected = resolve_decisions(context.frame_map, document["interpretation"], overrides)
    if not _same(leaf["intervals"], expected):
        raise ValueError("Decision intervals differ from replayed overrides")

    def stable():
        base_stable()
        if any(file_digest(p) != digest for p, digest in snapshots):
            raise ValueError("Decision history changed during operation")

    stable()
    return leaf, context, stable


def update_decisions(asset: Path, path: Path, override: DecisionOverride) -> Path:
    path = path.expanduser().resolve(strict=True)
    leaf, context, stable = load_decisions(asset, path)
    overrides = tuple(DecisionOverride(**row) for row in leaf["overrides"]) + (override,)
    evidence = read_json(project_path(context.root, leaf["interpretation"]["path"]))[
        "interpretation"
    ]
    return _publish(
        context,
        asset,
        project_path(context.root, leaf["interpretation"]["path"]),
        project_path(context.root, leaf["observation"]["path"]),
        leaf["interpretation"]["sha256"],
        leaf["observation"]["sha256"],
        overrides,
        {"path": path.relative_to(context.root).as_posix(), "sha256": file_digest(path)},
        evidence,
        stable,
    )


def decision_plan(asset: Path, path: Path, fps, audio: str, audio_stream: int | None) -> Path:
    path = path.expanduser().resolve(strict=True)
    leaf, context, stable = load_decisions(asset, path)
    cuts = included_cuts(leaf["intervals"])
    stable()
    target = create_plan(
        asset,
        context.frame_map.stream_index,
        cuts,
        fps,
        audio,
        audio_stream,
        decision_reference={
            "path": path.relative_to(context.root).as_posix(),
            "sha256": file_digest(path),
        },
    )

    stable()
    return target


def validate_decision_plan(root, plan_document, asset, frame_map, timeline):
    reference = plan_document["decision_reference"]
    path = project_path(root, reference["path"])
    if file_digest(path) != reference["sha256"]:
        raise ValueError("Timeline decision snapshot checksum changed")
    leaf, context, stable = load_decisions(asset, path)
    bounds = context.frame_map.boundaries()
    expected = tuple(
        SourceRange(
            context.frame_map.asset_id,
            context.frame_map.stream_index,
            bounds[a],
            bounds[b],
            context.frame_map.time_base,
        )
        for a, b in included_cuts(leaf["intervals"])
    )
    if frame_map != context.frame_map or timeline.cuts != expected:
        raise ValueError("Timeline cuts differ from its bound decisions")

    def check():
        stable()
        if file_digest(path) != reference["sha256"]:
            raise ValueError("Timeline decision snapshot checksum changed")

    check()
    return check
