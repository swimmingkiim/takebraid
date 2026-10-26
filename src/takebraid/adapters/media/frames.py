"""Spool selected decoded frame fields to disk, then parse one frame per line."""

import math
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

from takebraid.adapters.media.probe import ProbeError, _integer
from takebraid.domain.frames import FrameObservation


def parse_frame_lines(
    lines: Iterable[str], stream_index: int, *, max_frames: int = 250000
) -> tuple[FrameObservation, ...]:
    frames = []
    for line in lines:
        # Unselected side-data fields can appear on compact output lines. Only
        # numeric frame keys are consumed; all text remains untrusted/ignored.
        fields = {}
        for part in line.strip().split("|"):
            key, separator, value = part.partition("=")
            if separator and key in {
                "stream_index",
                "pts",
                "duration",
                "pkt_duration",
                "best_effort_timestamp",
            }:
                if key in fields:
                    raise ProbeError(f"Duplicate frame field: {key}")
                fields[key] = value
        if not fields:
            continue
        index = _integer(fields.get("stream_index"), "frame.stream_index", 0)
        if index != stream_index:
            raise ProbeError("Frame stream identity does not match selected stream")
        duration = _integer(fields.get("duration"), "frame.duration")
        if duration is None:
            duration = _integer(fields.get("pkt_duration"), "frame.pkt_duration")
        frames.append(
            FrameObservation(
                pts=_integer(fields.get("pts"), "frame.pts"),
                duration=duration,
                best_effort_timestamp=_integer(
                    fields.get("best_effort_timestamp"), "frame.best_effort_timestamp"
                ),
            )
        )
        if len(frames) > max_frames:
            raise ProbeError(f"Decoded frame count exceeds limit {max_frames}; raise --max-frames")
    return tuple(frames)


def decode_frames(
    source: Path, stream_index: int, *, timeout: float = 300, max_frames: int = 250000
) -> tuple[FrameObservation, ...]:
    if isinstance(stream_index, bool) or not isinstance(stream_index, int) or stream_index < 0:
        raise ProbeError("Stream index must be a nonnegative integer")
    if not math.isfinite(timeout) or timeout <= 0 or max_frames <= 0:
        raise ProbeError("Timeout and frame limit must be positive and finite")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-select_streams",
        str(stream_index),
        "-show_frames",
        "-show_entries",
        "frame=stream_index,pts,best_effort_timestamp,duration,pkt_duration:frame_side_data=",
        "-of",
        "compact=p=0:nk=0",
        str(source),
    ]
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors,
    ):
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=errors,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProbeError(
                "FFprobe not found; install FFmpeg/ffprobe and add it to PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProbeError("Frame scan timed out; raise --timeout for longer sources") from exc
        errors.seek(0)
        # Decode errors may coexist with exit code 0; do not certify a partial map.
        diagnostic = errors.read(4000).strip()
        if result.returncode or diagnostic:
            raise ProbeError(f"Frame decoding failed: {diagnostic or result.returncode}")
        output.seek(0)
        return parse_frame_lines(output, stream_index, max_frames=max_frames)
