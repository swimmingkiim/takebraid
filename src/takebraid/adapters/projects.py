"""Serialized project updates with immutable revision snapshots."""

import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from takebraid.adapters.artifacts import replace_json, write_new_json
from takebraid.adapters.identity import verify_source
from takebraid.adapters.records import RecordError, absolute_locator, load_asset, read_json
from takebraid.domain.time import _require_int


def project_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or absolute_locator(relative):
        raise RecordError("Project artifact path must be relative")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise RecordError("Project artifact path escapes the project")
    return target


def load_project(root: Path) -> dict:
    document = read_json(project_path(root, "project.json"))
    try:
        _require_int(document["revision"], "revision")
        if document["revision"] < 0 or not isinstance(document["project_id"], str):
            raise RecordError("Invalid project identity/revision")
        uuid.UUID(document["project_id"])
        if not isinstance(document["assets"], dict):
            raise RecordError("Project assets must be an object")
        for asset_id, entry in document["assets"].items():
            asset = load_asset(project_path(root, entry["metadata_path"]))
            if asset["asset_id"] != asset_id:
                raise RecordError("Registry asset identity does not match metadata")
            if not absolute_locator(entry["source_locator"]):
                raise RecordError("Registry source locator must be absolute")
        return document
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RecordError(f"Invalid project registry: {exc}") from exc


@contextmanager
def _lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".project.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RecordError(
            "Project is locked; wait, or inspect/remove a stale .project.lock"
        ) from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _new_project() -> dict:
    return {
        "schema_version": "0.1",
        "project_id": str(uuid.uuid4()),
        "revision": -1,
        "assets": {},
        "annotations": {},
    }


def _save(root: Path, document: dict) -> dict:
    history = root / "history"
    revisions = [document["revision"]]
    if history.exists():
        for file in history.glob("project-*.json"):
            match = re.fullmatch(r"project-(\d+)\.json", file.name)
            if match:
                revisions.append(int(match[1]))
    document["revision"] = max(revisions) + 1
    write_new_json(project_path(root, f"history/project-{document['revision']:06d}.json"), document)
    replace_json(root / "project.json", document)
    return document


def init_project(root: Path) -> dict:
    root = root.expanduser().resolve()
    with _lock(root):
        if (root / "project.json").exists():
            return load_project(root)
        return _save(root, _new_project())


def register_asset(root: Path, asset_path: Path) -> dict:
    root = root.expanduser().resolve()
    asset_path = asset_path.resolve()
    if not asset_path.is_relative_to(root):
        raise RecordError("Metadata must be inside the project; media can remain outside")
    asset = load_asset(asset_path)
    entry = {
        "metadata_path": asset_path.relative_to(root).as_posix(),
        "source_locator": asset["source"]["locator"],
    }
    with _lock(root):
        document = load_project(root) if (root / "project.json").exists() else _new_project()
        previous = document["assets"].get(asset["asset_id"])
        if previous is not None:
            if previous["metadata_path"] != entry["metadata_path"]:
                raise RecordError(
                    "Asset already has metadata; use relink to change the source path"
                )
            return document
        document["assets"][asset["asset_id"]] = entry
        return _save(root, document)


def relink_asset(root: Path, asset_id: str, source: Path) -> dict:
    root = root.expanduser().resolve()
    source = source.expanduser().resolve(strict=True)
    with _lock(root):
        document = load_project(root)
        if asset_id not in document["assets"]:
            raise RecordError("Asset is not registered in this project")
        asset = load_asset(project_path(root, document["assets"][asset_id]["metadata_path"]))
        verify_source(source, asset["source"]["fingerprint"]["digest"])
        document["assets"][asset_id]["source_locator"] = str(source)
        return _save(root, document)


def asset_source(asset_path: Path, asset: dict) -> tuple[Path, Path]:
    # Canonical ingest layout; standalone legacy assets retain a local stage folder.
    root = asset_path.parent
    if root.name == asset["asset_id"] and root.parent.name == "assets":
        root = root.parent.parent
    locator = asset["source"]["locator"]
    if (root / "project.json").exists():
        project = load_project(root)
        entry = project["assets"].get(asset["asset_id"])
        if entry is not None:
            if project_path(root, entry["metadata_path"]) != asset_path:
                raise RecordError("Asset path does not match registry metadata")
            locator = entry["source_locator"]
    return root, Path(locator)


def verify_project(root: Path) -> dict[str, str]:
    document = load_project(root)
    results = {}
    for asset_id, entry in document["assets"].items():
        asset = load_asset(project_path(root, entry["metadata_path"]))
        try:
            verify_source(Path(entry["source_locator"]), asset["source"]["fingerprint"]["digest"])
            results[asset_id] = "verified"
        except (OSError, ValueError) as exc:
            results[asset_id] = str(exc)
    return results
