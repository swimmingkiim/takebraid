import json

import pytest

from takebraid.adapters.projects import (
    init_project,
    load_project,
    register_asset,
    relink_asset,
    verify_project,
)
from takebraid.application.ingest import ingest
from takebraid.cli import main


@pytest.fixture
def project_asset(tmp_path, monkeypatch, probe_metadata):
    source = tmp_path / "source.mov"
    source.write_bytes(b"source-one")
    root = tmp_path / "project"
    monkeypatch.setattr("takebraid.application.ingest.probe_media", lambda _: probe_metadata)
    asset = ingest(source, root)
    return root, asset, source


def test_ingest_registers_asset_and_init_is_idempotent(project_asset):
    root, asset, _ = project_asset
    project = load_project(root)
    asset_id = json.loads(asset.read_text())["asset_id"]
    assert project["assets"][asset_id]["metadata_path"] == asset.relative_to(root).as_posix()
    assert init_project(root) == project
    assert register_asset(root, asset) == project


def test_relink_missing_source_preserves_metadata_and_annotations(project_asset, tmp_path):
    root, asset, source = project_asset
    original = asset.read_bytes()
    project = load_project(root)
    project["annotations"] = {"editor": "keep the final reveal"}
    (root / "project.json").write_text(json.dumps(project))
    moved = tmp_path / "moved.mov"
    source.rename(moved)
    asset_id = json.loads(original)["asset_id"]
    updated = relink_asset(root, asset_id, moved)
    assert updated["revision"] > project["revision"]
    assert updated["annotations"] == project["annotations"]
    assert updated["assets"][asset_id]["source_locator"] == str(moved)
    assert asset.read_bytes() == original
    assert verify_project(root) == {asset_id: "verified"}
    snapshots = list((root / "history").glob("project-*.json"))
    assert len(snapshots) == 2
    assert any(
        json.loads(path.read_text())["assets"][asset_id]["source_locator"] == str(source)
        for path in snapshots
    )


def test_relink_wrong_content_preserves_current_registry(project_asset, tmp_path):
    root, asset, _ = project_asset
    before = (root / "project.json").read_bytes()
    wrong = tmp_path / "wrong.mov"
    wrong.write_bytes(b"different")
    with pytest.raises(ValueError, match="fingerprint changed"):
        relink_asset(root, json.loads(asset.read_text())["asset_id"], wrong)
    assert (root / "project.json").read_bytes() == before
    assert not (root / ".project.lock").exists()


def test_project_verify_reports_missing_and_changed_sources(project_asset):
    root, asset, source = project_asset
    asset_id = json.loads(asset.read_text())["asset_id"]
    source.write_bytes(b"changed")
    assert "fingerprint changed" in verify_project(root)[asset_id]
    source.unlink()
    assert "relink" in verify_project(root)[asset_id]


def test_lock_conflict_does_not_remove_another_writers_lock(project_asset):
    root, _, _ = project_asset
    lock = root / ".project.lock"
    lock.write_text("another writer")
    with pytest.raises(ValueError, match="locked"):
        init_project(root)
    assert lock.read_text() == "another writer"


def test_failed_registry_publish_keeps_current_and_retry_preserves_orphan_snapshot(
    project_asset, tmp_path, monkeypatch
):
    root, asset, source = project_asset
    before = (root / "project.json").read_bytes()
    moved = tmp_path / "moved.mov"
    moved.write_bytes(source.read_bytes())
    from takebraid.adapters.artifacts import replace_json

    def fail(*args, **kwargs):
        raise OSError("simulated atomic publication failure")

    monkeypatch.setattr("takebraid.adapters.projects.replace_json", fail)
    asset_id = json.loads(asset.read_text())["asset_id"]
    with pytest.raises(OSError, match="publication"):
        relink_asset(root, asset_id, moved)
    assert (root / "project.json").read_bytes() == before
    monkeypatch.setattr("takebraid.adapters.projects.replace_json", replace_json)
    assert relink_asset(root, asset_id, moved)["revision"] == 2
    assert len(list((root / "history").glob("project-*.json"))) == 3


def test_registry_rejects_traversal_and_unknown_schema(project_asset):
    root, asset, _ = project_asset
    project = load_project(root)
    asset_id = json.loads(asset.read_text())["asset_id"]
    project["assets"][asset_id]["metadata_path"] = "../outside.json"
    (root / "project.json").write_text(json.dumps(project))
    with pytest.raises(ValueError, match="escapes"):
        load_project(root)
    project["schema_version"] = "99"
    (root / "project.json").write_text(json.dumps(project))
    with pytest.raises(ValueError, match="schema"):
        load_project(root)


def test_project_cli_verify_exit_status_and_show(project_asset, capsys):
    root, _, source = project_asset
    assert main(["project", "show", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["assets"]
    assert main(["project", "verify", str(root)]) == 0
    source.unlink()
    assert main(["project", "verify", str(root)]) == 2
