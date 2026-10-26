import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from takebraid.adapters.media.frames import decode_frames, parse_frame_lines
from takebraid.adapters.media.probe import ProbeError


def test_compact_frames_preserve_raw_pts_and_legacy_duration():
    frames = parse_frame_lines(
        [
            "stream_index=2|pts=-40|best_effort_timestamp=-40|duration=40\n",
            "stream_index=2|pts=0|pkt_duration=80\n",
            "stream_index=2|pts=N/A|best_effort_timestamp=80|duration=40\n",
        ],
        2,
    )
    assert frames[0].pts == -40
    assert frames[1].duration == 80
    assert frames[2].pts is None
    assert frames[2].best_effort_timestamp == 80


@pytest.mark.parametrize(
    "line",
    [
        "stream_index=0|pts=1.5",
        "stream_index=1|pts=0",
        "pts=0",
        "stream_index=0|pts=0|pts=1",
        "stream_index=0|duration=NaN",
    ],
)
def test_malformed_or_wrong_stream_frame_is_rejected(line):
    with pytest.raises(ProbeError):
        parse_frame_lines([line], 0)


def test_frame_limit_is_explicit():
    with pytest.raises(ProbeError, match="frame count exceeds"):
        parse_frame_lines(["stream_index=0|pts=0", "stream_index=0|pts=40"], 0, max_frames=1)


def test_decode_spools_output_and_rejects_decoder_errors_even_on_zero_exit(monkeypatch):
    def run(command, **kwargs):
        assert command[-1] == str(Path("/tmp/source ; name.mov"))
        assert command[command.index("-select_streams") + 1] == "2"
        assert "shell" not in kwargs
        kwargs["stdout"].write("stream_index=2|pts=0|duration=1\n")
        kwargs["stderr"].write("corrupt frame detected")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("takebraid.adapters.media.frames.subprocess.run", run)
    with pytest.raises(ProbeError, match="corrupt frame"):
        decode_frames(Path("/tmp/source ; name.mov"), 2)


@pytest.mark.parametrize(
    "failure,message",
    [
        (FileNotFoundError(), "not found"),
        (subprocess.TimeoutExpired("ffprobe", 1), "timed out"),
    ],
)
def test_decode_execution_failures(monkeypatch, failure, message):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr("takebraid.adapters.media.frames.subprocess.run", run)
    with pytest.raises(ProbeError, match=message):
        decode_frames(Path("/tmp/video.mov"), 0)


@pytest.mark.parametrize("timeout,limit", [(0, 10), (float("nan"), 10), (1, 0)])
def test_invalid_scan_limits(timeout, limit):
    with pytest.raises(ProbeError, match="positive"):
        decode_frames(Path("/tmp/video.mov"), 0, timeout=timeout, max_frames=limit)
