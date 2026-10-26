import json

import pytest

from takebraid.adapters.artifacts import to_json_value
from takebraid.adapters.records import RecordError, load_asset, load_frame_map, read_json
from takebraid.application.ingest import ingest
from takebraid.domain.frames import FrameMap, FrameObservation
from takebraid.domain.time import SourceRange, TimeBase


@pytest.mark.parametrize(
    "content",
    [
        '{"schema_version":"0.1","schema_version":"0.1"}',
        '{"schema_version":"0.1","value":NaN}',
        '{"schema_version":"0.1","value":1e999}',
        '{"schema_version":"2"}',
    ],
)
def test_record_reader_rejects_ambiguous_nonfinite_or_unknown_documents(tmp_path, content):
    path = tmp_path / "record.json"
    path.write_text(content)
    with pytest.raises(RecordError):
        read_json(path)


def test_asset_loader_checks_clocks_and_fingerprint(tmp_path, monkeypatch, probe_metadata):
    source = tmp_path / "source.mov"
    source.write_bytes(b"media")
    monkeypatch.setattr("takebraid.application.ingest.probe_media", lambda _: probe_metadata)
    path = ingest(source, tmp_path / "project")
    document = load_asset(path)
    document["metadata"]["streams"][0]["time_base"]["denominator"] = 0
    path.write_text(json.dumps(document))
    with pytest.raises(RecordError, match="denominator"):
        load_asset(path)
    document["source"]["fingerprint"]["digest"] = "bad"
    path.write_text(json.dumps(document))
    with pytest.raises(RecordError, match="identity"):
        load_asset(path)


@pytest.mark.parametrize("locator", [r"C:\shoot\clip.mov", "/other-machine/clip.mov"])
def test_cross_platform_absolute_locator_remains_readable_for_relinking(
    tmp_path, monkeypatch, probe_metadata, locator
):
    source = tmp_path / "source.mov"
    source.write_bytes(b"media")
    monkeypatch.setattr("takebraid.application.ingest.probe_media", lambda _: probe_metadata)
    path = ingest(source, tmp_path / "project")
    document = load_asset(path)
    document["source"]["locator"] = locator
    path.write_text(json.dumps(document))
    assert load_asset(path)["source"]["locator"] == locator


def test_frame_loader_rederives_status_and_boundaries(tmp_path):
    asset_id = "sha256-" + "a" * 64
    frame_map = FrameMap(
        asset_id, 0, TimeBase(1, 25), (FrameObservation(0, 1), FrameObservation(1, 1))
    )
    document = {
        "schema_version": "0.1",
        "frame_map": frame_map,
        "status": "ready",
        "issues": [],
        "cadence": frame_map.cadence,
        "presentation_end_pts": 2,
        "provenance": {"source_sha256": "a" * 64},
    }
    path = tmp_path / "frames.json"
    path.write_text(json.dumps(to_json_value(document)))
    loaded = load_frame_map(path)
    loaded.validate_range(SourceRange(asset_id, 0, 0, 2, TimeBase(1, 25)))
    altered = json.loads(path.read_text())
    altered["frame_map"]["frames"][1]["pts"] = 0
    path.write_text(json.dumps(altered))
    with pytest.raises(RecordError, match="summary disagrees"):
        load_frame_map(path)
