import hashlib
import json
from pathlib import Path

import pytest

from takebraid.adapters.artifacts import write_new_json
from takebraid.application.ingest import IngestError, ingest
from takebraid.cli import main


@pytest.fixture
def source(tmp_path, monkeypatch, probe_metadata):
    video = tmp_path / "source.mov"
    video.write_bytes(b"synthetic source bytes")
    monkeypatch.setattr(
        "takebraid.application.ingest.probe_media",
        lambda _: probe_metadata,
    )
    return video


def test_ingest_writes_full_fingerprint_and_preserves_source(source, tmp_path):
    before = source.read_bytes()
    output = ingest(source, tmp_path / "project")
    document = json.loads(output.read_text())
    digest = hashlib.sha256(before).hexdigest()
    assert document["schema_version"] == "0.1"
    assert document["asset_id"] == f"sha256-{digest}"
    assert document["source"]["fingerprint"] == {"algorithm": "sha256", "digest": digest}
    assert document["source"]["locator"] == str(source.resolve())
    assert document["timing_status"] == "metadata_only_unverified_frame_timestamps"
    assert source.read_bytes() == before


def test_repeat_ingest_never_overwrites_existing_metadata(source, tmp_path):
    project = tmp_path / "project"
    output = ingest(source, project)
    output.write_text("editor data")
    with pytest.raises(IngestError, match="already registered"):
        ingest(source, project)
    assert output.read_text() == "editor data"


def test_duplicate_bytes_have_same_identity_in_other_projects(source, tmp_path):
    other = tmp_path / "renamed.mov"
    other.write_bytes(source.read_bytes())
    first = ingest(source, tmp_path / "project-a")
    second = ingest(other, tmp_path / "project-b")
    assert first.parent.name == second.parent.name


def test_source_change_during_probe_is_rejected(source, tmp_path, monkeypatch):
    def changing_probe(path):
        path.write_bytes(b"changed source")

    monkeypatch.setattr("takebraid.application.ingest.probe_media", changing_probe)
    with pytest.raises(IngestError, match="Source changed"):
        ingest(source, tmp_path / "project")
    assert not (tmp_path / "project").exists()


def test_missing_or_non_file_source(tmp_path):
    with pytest.raises(IngestError):
        ingest(tmp_path / "missing", tmp_path / "project")
    with pytest.raises(IngestError, match="regular local"):
        ingest(tmp_path, tmp_path / "project")


def test_project_cannot_be_source_file(source):
    with pytest.raises(IngestError, match="directory"):
        ingest(source, source)


def test_publish_failure_cleans_temp_and_keeps_existing_file(tmp_path):
    output = tmp_path / "asset.json"
    output.write_text("original")
    with pytest.raises(FileExistsError):
        write_new_json(output, {"new": True})
    assert output.read_text() == "original"
    assert list(tmp_path.glob(".asset-*.tmp")) == []


def test_cli_ingest_success_and_failure(source, tmp_path, capsys):
    assert main(["ingest", str(source), "--project", str(tmp_path / "project")]) == 0
    output = Path(capsys.readouterr().out.strip())
    assert output.is_file()
    assert main(["ingest", str(source), "--project", str(tmp_path / "project")]) == 1
    assert "already registered" in capsys.readouterr().err
