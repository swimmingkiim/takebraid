import subprocess
import time
from fractions import Fraction
from types import SimpleNamespace

import pytest

from takebraid.adapters.media.probe import ProbeError
from takebraid.adapters.media.render import audio_filter, run_media, video_filter
from takebraid.domain.time import SourceRange, TimeBase
from takebraid.domain.timeline import ClipLayout, ManualTimeline


def test_filters_use_verified_source_frames_not_time_seeking():
    cut = SourceRange("asset", 0, -1001, 1001, TimeBase(1, 30000))
    clip = ClipLayout(cut, 3, 5, 0, 2, 0, 3203)
    timeline = ManualTimeline("asset", 0, cut.time_base, Fraction(30000, 1001), (cut,), "source", 1)
    assert "start_frame=3:end_frame=5" in video_filter(clip, timeline)
    assert "round=up" in video_filter(clip, timeline)
    assert "start_pts=-1601:end_pts=1602" in audio_filter(clip)
    assert "whole_len=3203" in audio_filter(clip)


def test_execution_uses_arguments_no_shell_and_refuses_error_diagnostics(monkeypatch, tmp_path):
    def run(command, **kwargs):
        assert command[-1] == "file ; name.mov"
        assert "shell" not in kwargs
        kwargs["stderr"].write("decoder error")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("takebraid.adapters.media.render.subprocess.run", run)
    with pytest.raises(ProbeError, match="decoder error"):
        run_media(["ffmpeg", "file ; name.mov"], deadline=time.monotonic() + 1, cwd=tmp_path)


@pytest.mark.parametrize(
    "error,message",
    [(FileNotFoundError(), "not found"), (subprocess.TimeoutExpired("ffmpeg", 1), "timed out")],
)
def test_renderer_errors_are_actionable(monkeypatch, error, message):
    def run(*args, **kwargs):
        raise error

    monkeypatch.setattr("takebraid.adapters.media.render.subprocess.run", run)
    with pytest.raises(ProbeError, match=message):
        run_media(["ffmpeg"], deadline=time.monotonic() + 1)


def test_elapsed_deadline_does_not_launch_a_process():
    with pytest.raises(ProbeError, match="timed out"):
        run_media(["ffmpeg"], deadline=time.monotonic() - 1)
