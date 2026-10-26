import hashlib
import json
from pathlib import Path

import pytest

from takebraid.adapters.artifacts import to_json_value
from takebraid.application.scan import ScanError, scan_asset
from takebraid.cli import main
from takebraid.domain.frames import FrameObservation
from takebraid.domain.metadata import ProbeMetadata, StreamMetadata
from takebraid.domain.time import TimeBase


@pytest.fixture
def registered(tmp_path, monkeypatch):
    source = tmp_path / "source.mov"
    source.write_bytes(b"stable source")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    asset = tmp_path / "project" / "asset.json"
    asset.parent.mkdir()
    asset.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "asset_id": f"sha256-{digest}",
                "source": {
                    "locator": str(source),
                    "fingerprint": {"algorithm": "sha256", "digest": digest},
                },
            }
        )
    )
    stream = StreamMetadata(
        index=0,
        kind="video",
        codec="test",
        time_base=TimeBase(1, 1000),
        start_pts=0,
        duration_ts=80,
        reported_start_seconds=None,
        reported_duration_seconds=None,
        average_frame_rate=None,
        nominal_frame_rate=None,
        width=64,
        height=48,
        rotation_degrees=None,
        display_matrix=None,
        pixel_format=None,
        color_range=None,
        color_space=None,
        color_transfer=None,
        color_primaries=None,
        sample_rate=None,
        channels=None,
        channel_layout=None,
        attached_picture=False,
    )
    monkeypatch.setattr(
        "takebraid.application.scan.probe_media",
        lambda _: ProbeMetadata(
            "test",
            None,
            None,
            (stream,),
            "test-version",
            (),
        ),
    )
    document = json.loads(asset.read_text())
    document["source"].update(
        {"size_bytes": source.stat().st_size, "mtime_ns": source.stat().st_mtime_ns}
    )
    document["metadata"] = to_json_value(
        ProbeMetadata("test", None, None, (stream,), "test-version", ())
    )
    asset.write_text(json.dumps(document))
    monkeypatch.setattr(
        "takebraid.application.scan.decode_frames",
        lambda *a, **k: (
            FrameObservation(0, 40),
            FrameObservation(40, 40),
        ),
    )
    return asset, source


def test_verified_map_is_published_without_updating_asset(registered):
    asset, source = registered
    original = asset.read_bytes()
    output, status = scan_asset(asset, 0)
    assert status == "ready"
    result = json.loads(output.read_text())
    assert result["presentation_end_pts"] == 80
    assert result["frame_map"]["stream_index"] == 0
    assert asset.read_bytes() == original
    assert source.read_bytes() == b"stable source"
    assert scan_asset(asset, 0)[0] == output


def test_changed_source_refused_before_decode(registered):
    asset, source = registered
    source.write_bytes(b"modified")
    with pytest.raises(ScanError, match="fingerprint changed"):
        scan_asset(asset, 0)
    assert list(asset.parent.glob("stages/*/attempts/*/frames.json")) == []


def test_change_during_decode_does_not_publish(registered, monkeypatch):
    asset, source = registered

    def change(*args, **kwargs):
        source.write_bytes(b"changed during decode")
        return (FrameObservation(0, 40),)

    monkeypatch.setattr("takebraid.application.scan.decode_frames", change)
    with pytest.raises(ScanError, match="Source changed"):
        scan_asset(asset, 0)
    assert list(asset.parent.glob("stages/*/attempts/*/frames.json")) == []


def test_explicit_stream_selection_is_checked(registered):
    with pytest.raises(ScanError, match="Select a video stream"):
        scan_asset(registered[0], 4)


@pytest.mark.parametrize(
    "content", ["{", "[]", '{"schema_version":"9"}', '{"schema_version":"0.1"}']
)
def test_invalid_asset_file(tmp_path, content):
    path = tmp_path / "asset.json"
    path.write_text(content)
    with pytest.raises(ScanError):
        scan_asset(path, 0)


def test_cli_diagnostic_map_has_exit_two(registered, monkeypatch, capsys):
    asset, _ = registered
    monkeypatch.setattr(
        "takebraid.application.scan.decode_frames", lambda *a, **k: (FrameObservation(None, 40, 0),)
    )
    assert main(["scan", str(asset), "--stream", "0"]) == 2
    captured = capsys.readouterr()
    assert "unsupported" in captured.err
    result = json.loads(Path(captured.out.strip()).read_text())
    assert result["status"] == "unsupported"
    assert result["frame_map"]["frames"][0]["pts"] is None


def test_cache_hit_does_not_decode_again_and_force_preserves_prior_output(registered, monkeypatch):
    asset, _ = registered
    first, _ = scan_asset(asset, 0)
    before = first.read_bytes()

    def no_decode(*args, **kwargs):
        raise AssertionError("cache hit must not decode")

    monkeypatch.setattr("takebraid.application.scan.decode_frames", no_decode)
    assert scan_asset(asset, 0)[0] == first
    monkeypatch.setattr(
        "takebraid.application.scan.decode_frames",
        lambda *a, **k: (
            FrameObservation(0, 40),
            FrameObservation(40, 40),
        ),
    )
    second, _ = scan_asset(asset, 0, force=True)
    assert first != second
    assert first.read_bytes() == before
    assert scan_asset(asset, 0)[0] == second


def test_tampered_cached_artifact_requires_recompute(registered):
    asset, _ = registered
    first, _ = scan_asset(asset, 0)
    first.write_text("partial or changed output")
    with pytest.raises(ScanError, match="checksum mismatch"):
        scan_asset(asset, 0)
    second, status = scan_asset(asset, 0, force=True)
    assert status == "ready"
    assert second != first
    assert first.read_text() == "partial or changed output"


def test_failed_forced_run_preserves_previous_cache(registered, monkeypatch):
    asset, _ = registered
    first, _ = scan_asset(asset, 0)

    def fail(*args, **kwargs):
        raise OSError("interrupted decode")

    monkeypatch.setattr("takebraid.application.scan.decode_frames", fail)
    with pytest.raises(ScanError, match="interrupted decode"):
        scan_asset(asset, 0, force=True)
    assert scan_asset(asset, 0)[0] == first


@pytest.mark.parametrize(
    "failure,state", [(RuntimeError("decode failed"), "failed"), (KeyboardInterrupt(), "cancelled")]
)
def test_scan_records_failed_or_cancelled_attempts(registered, monkeypatch, failure, state):
    asset, _ = registered

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("takebraid.application.scan.decode_frames", fail)
    with pytest.raises(type(failure)):
        scan_asset(asset, 0)
    receipts = list(asset.parent.glob("stages/*/attempts/*/receipt.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["status"] == state
    assert list(asset.parent.glob("stages/*/completed.json")) == []
