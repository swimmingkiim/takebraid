"""Explicit local evaluation manifests, rights declarations and shoot-level split audits."""

import re
from pathlib import Path

from takebraid.adapters.records import load_asset, read_json
from takebraid.domain.evaluation import DEFECTS


def local_path(manifest: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or "://" in value:
        raise ValueError("Evaluation inputs must be explicit local paths")
    return (manifest.parent / value).expanduser().resolve(strict=True)


def load_manifest(path: Path) -> dict:
    document = read_json(path, limit=8 * 1024 * 1024)
    for name in ("dataset_id", "label_version"):
        if not isinstance(document[name], str) or not re.fullmatch(
            r"[a-zA-Z0-9_-]{1,80}", document[name]
        ):
            raise ValueError("Dataset and label versions need short identifiers")
    registry = document["policy_registry"]
    if (
        not isinstance(registry, dict)
        or not registry
        or set(registry) - DEFECTS
        or any(
            not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v)
            for v in registry.values()
        )
    ):
        raise ValueError("Policy registry must pin supported defect classes to SHA-256 digests")
    entries = document["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 200:
        raise ValueError("Evaluation requires 1..200 entries")
    identities = set()
    groups = {key: {} for key in ("project_id", "shoot_id", "asset_id")}
    seen = set()
    for entry in entries:
        if (
            not isinstance(entry["id"], str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", entry["id"])
            or entry["id"] in identities
        ):
            raise ValueError("Duplicate or invalid evaluation entry identity")
        identities.add(entry["id"])
        if entry["split"] not in {"calibration", "test"} or entry["kind"] not in {
            "synthetic",
            "camera",
        }:
            raise ValueError(
                "Entry needs explicit calibration/test split and synthetic/camera kind"
            )
        if entry["defect"] not in registry:
            raise ValueError("Entry defect lacks a pinned policy")
        if entry["label_method"] != ("constructed" if entry["kind"] == "synthetic" else "human"):
            raise ValueError("Camera labels must be human; synthetic labels must be constructed")
        if (
            not isinstance(entry["annotation_protocol"], str)
            or not entry["annotation_protocol"].strip()
            or len(entry["annotation_protocol"]) > 2000
        ):
            raise ValueError("An explicit annotation protocol is required")
        raters = entry["annotators"]
        if (
            not isinstance(raters, list)
            or not 2 <= len(raters) <= 10
            or len(set(raters)) != len(raters)
            or any(
                not isinstance(r, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", r)
                for r in raters
            )
        ):
            raise ValueError("Entry requires 2..10 distinct annotator identifiers")
        if not isinstance(entry["scene"], str) or not re.fullmatch(
            r"[a-zA-Z0-9_-]{1,80}", entry["scene"]
        ):
            raise ValueError("Entry needs a scene/failure-case identifier")
        rights = entry["rights"]
        for name in ("source", "license", "permission_evidence"):
            if (
                not isinstance(rights[name], str)
                or not rights[name].strip()
                or len(rights[name]) > 2000
            ):
                raise ValueError("Explicit source/license/permission evidence is required")
        if rights["evaluation_permitted"] is not True:
            raise ValueError("Evaluation permission must be explicitly declared")
        asset = load_asset(local_path(path, entry["asset"]))
        for key in groups:
            value = asset["asset_id"] if key == "asset_id" else entry[key]
            if not isinstance(value, str) or not value or len(value) > 100:
                raise ValueError("Project/shoot grouping must be explicit")
            if value in groups[key] and groups[key][value] != entry["split"]:
                raise ValueError(f"Split leakage: {key} spans calibration and test")
            groups[key][value] = entry["split"]
        identity = (asset["asset_id"], entry["defect"])
        if identity in seen:
            raise ValueError("Duplicate source/defect would double-count evaluation")
        seen.add(identity)
        labels = entry["labels"]
        if not isinstance(labels, list) or not 1 <= len(labels) <= 250000:
            raise ValueError("Entry requires explicit full-coverage labels")
        for label in labels:
            if set(label["votes"]) != set(raters):
                raise ValueError("Every label interval must retain all annotator votes")
    return document
