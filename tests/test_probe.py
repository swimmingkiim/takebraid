import json
import subprocess
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from takebraid.adapters.media.probe import ProbeError, parse_probe, probe_media
from takebraid.domain.time import TimeBase


@pytest.fixture
def probe_document():
    return {
        "program_version": {"version": "test-1"},
        "format": {"format_name": "mov,mp4", "start_time": "-0.033367", "duration": "1.001"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "time_base": "1/30000",
                "start_pts": -1001,
                "duration_ts": 30030,
                "avg_frame_rate": "30000/1001",
                "r_frame_rate": "30000/1001",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
                "tags": {"rotate": "90"},
                "side_data_list": [
                    {
                        "side_data_type": "Display Matrix",
                        "rotation": -90,
                        "displaymatrix": "test matrix",
                    }
                ],
            }
        ],
    }


def test_preserves_exact_clock_negative_pts_rotation_and_color(probe_document):
    result = parse_probe(json.dumps(probe_document))
    stream = result.streams[0]
    assert stream.time_base == TimeBase(1, 30000)
    assert stream.start_pts == -1001
    assert stream.duration_ts == 30030
    assert stream.average_frame_rate == Fraction(30000, 1001)
    assert stream.rotation_degrees == -90
    assert stream.display_matrix == "test matrix"
    assert stream.color_space == "bt709"
    assert result.reported_duration_seconds == Fraction(1001, 1000)
    assert result.reported_start_seconds == Fraction(-33367, 1000000)
    assert result.warnings == ("frame_timestamps_not_scanned",)


def test_retains_all_streams_and_does_not_choose_primary(probe_document):
    probe_document["streams"].extend(
        [
            {
                "index": 1,
                "codec_type": "audio",
                "time_base": "1/48000",
                "sample_rate": "48000",
                "channels": 2,
                "channel_layout": "stereo",
            },
            {
                "index": 2,
                "codec_type": "video",
                "time_base": "1/1000",
                "start_pts": 2500,
                "avg_frame_rate": "24000/1001",
                "r_frame_rate": "30/1",
            },
            {"index": 3, "codec_type": "subtitle"},
        ]
    )
    result = parse_probe(json.dumps(probe_document))
    assert len(result.streams) == 4
    assert result.streams[1].sample_rate == 48000
    assert result.streams[1].channels == 2
    assert result.streams[2].start_pts == 2500
    assert result.streams[2].nominal_frame_rate == 30
    assert "multiple_video_streams_require_explicit_selection_before_editing" in result.warnings


def test_unknown_fields_remain_unknown(probe_document):
    video = probe_document["streams"][0]
    video.pop("start_pts")
    video["avg_frame_rate"] = "0/0"
    video["duration"] = "N/A"
    probe_document["format"].pop("duration")
    result = parse_probe(json.dumps(probe_document))
    assert result.streams[0].average_frame_rate is None
    assert result.streams[0].reported_duration_seconds is None
    assert "video_start_pts_unknown" in result.warnings
    assert "container_duration_unknown" in result.warnings


def test_numeric_decimal_metadata_does_not_round_through_float(probe_document):
    payload = json.dumps(probe_document).replace('"1.001"', "1.000000000000000001")
    result = parse_probe(payload)
    assert result.reported_duration_seconds == Fraction(1000000000000000001, 10**18)


@pytest.mark.parametrize(
    "field,value",
    [
        ("time_base", "0/0"),
        ("time_base", "-1/10"),
        ("time_base", None),
        ("start_pts", True),
        ("start_pts", 1.5),
        ("duration_ts", -1),
        ("avg_frame_rate", "NaN"),
        ("avg_frame_rate", "-1/1"),
        ("duration", "Infinity"),
        ("width", 0),
        ("side_data_list", {}),
    ],
)
def test_rejects_malformed_timing_and_stream_fields(probe_document, field, value):
    probe_document["streams"][0][field] = value
    with pytest.raises(ProbeError):
        parse_probe(json.dumps(probe_document))


@pytest.mark.parametrize("payload", ["{", "[]", "{}", '{"streams": []}'])
def test_rejects_invalid_documents(payload):
    with pytest.raises(ProbeError):
        parse_probe(payload)


def test_rejects_duplicate_stream_indices(probe_document):
    probe_document["streams"].append(probe_document["streams"][0])
    with pytest.raises(ProbeError, match="duplicate"):
        parse_probe(json.dumps(probe_document))


def test_cover_art_is_not_video_footage(probe_document):
    probe_document["streams"][0]["disposition"] = {"attached_pic": 1}
    with pytest.raises(ProbeError, match="cover pictures"):
        parse_probe(json.dumps(probe_document))


def test_probe_uses_argument_list_and_local_protocol_only(monkeypatch, probe_document):
    source = Path("/tmp/footage name;$(echo unsafe).mov")

    def run(command, **kwargs):
        assert command[-1] == str(source)
        assert command[command.index("-protocol_whitelist") + 1] == "file"
        assert kwargs.get("shell", False) is False
        assert kwargs["timeout"] == 30
        return SimpleNamespace(returncode=0, stdout=json.dumps(probe_document))

    monkeypatch.setattr("takebraid.adapters.media.probe.subprocess.run", run)
    assert probe_media(source).ffprobe_version == "test-1"


@pytest.mark.parametrize(
    "failure,message",
    [
        (FileNotFoundError(), "not found"),
        (subprocess.TimeoutExpired("ffprobe", 30), "timed out"),
    ],
)
def test_probe_execution_errors_are_actionable(monkeypatch, failure, message):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr("takebraid.adapters.media.probe.subprocess.run", run)
    with pytest.raises(ProbeError, match=message):
        probe_media(Path("/tmp/video.mov"))


def test_invalid_media_error(monkeypatch):
    monkeypatch.setattr(
        "takebraid.adapters.media.probe.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="Invalid data found"),
    )
    with pytest.raises(ProbeError, match="Invalid data"):
        probe_media(Path("/tmp/invalid.mov"))
