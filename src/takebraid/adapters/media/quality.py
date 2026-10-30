"""Bounded grayscale decoding with same-pass source PTS cross-checks."""

import re
import subprocess
import tempfile
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

from takebraid.domain.frames import FrameMap
from takebraid.domain.quality import QualitySettings
from takebraid.quality.metrics import measure_gray

MAX_DECODE_BYTES = 256 * 1024 * 1024
MAX_SAMPLES = 10000


def check_decode_log(lines, frame_map: FrameMap, source_geometry: tuple[int, int]) -> None:
    clock = None
    seen = 0
    for line in lines:
        if "[error]" in line or "[fatal]" in line:
            raise ValueError("FFmpeg reported a decode error")
        if "Parsed_showinfo_" not in line:
            continue
        config = re.search(r"config in time_base: (\d+)/(\d+)", line)
        if config:
            clock = Fraction(int(config[1]), int(config[2]))
        item = re.search(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:", line)
        if item:
            size = re.search(r"\bs:(\d+)x(\d+)\b", line)
            if (
                clock is None
                or seen >= len(frame_map.frames)
                or int(item[1]) != seen
                or clock * int(item[2]) != frame_map.time_base.seconds(frame_map.frames[seen].pts)
                or size is None
                or (int(size[1]), int(size[2])) != source_geometry
                or " i:P " not in line
            ):
                raise ValueError(
                    "Decoded analysis PTS/geometry/progressive scan differs from source map"
                )
            seen += 1
    if seen != len(frame_map.frames):
        raise ValueError("Decoded analysis frame count differs from source map")


@contextmanager
def _decoded_pixels(
    source: Path,
    frame_map: FrameMap,
    source_geometry: tuple[int, int],
    geometry: tuple[int, int],
    *,
    timeout: float,
    pixel_format: str = "gray",
    every: int = 1,
):
    """Yield a verified disk spool; close it on success, failure or cancellation."""
    width, height = geometry
    if type(every) is not int or every < 1:
        raise ValueError("Decoded frame stride must be a positive integer")
    channels = {"gray": 1, "rgb24": 3}[pixel_format]
    output_count = len(range(0, len(frame_map.frames), every))
    expected_bytes = output_count * width * height * channels
    if expected_bytes > MAX_DECODE_BYTES:
        raise ValueError("Decoded analysis exceeds 256 MiB budget")
    # Verify every decoded source frame before selecting by its integer decoded index.
    selection = f",select=not(mod(n\\,{every}))" if every > 1 else ""
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-v",
        "level+info",
        "-xerror",
        "-copyts",
        "-noautorotate",
        "-protocol_whitelist",
        "file",
        "-i",
        str(source),
        "-map",
        f"0:{frame_map.stream_index}",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        f"showinfo{selection},scale={width}:{height}:flags=area,format={pixel_format}",
        "-fps_mode",
        "passthrough",
        "-frames:v",
        str(output_count + 1),
        "-threads:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        pixel_format,
        "-",
    ]
    with (
        tempfile.TemporaryFile() as raw,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log,
    ):
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=raw,
            stderr=log,
            timeout=timeout,
            check=False,
        )
        log.seek(0)
        if result.returncode:
            raise ValueError(f"Analysis decode failed: {log.read(4000)}")
        check_decode_log(log, frame_map, source_geometry)
        if raw.seek(0, 2) != expected_bytes:
            raise ValueError("Decoded pixel length differs from source map")
        yield raw


@contextmanager
def decoded_gray(source, frame_map, source_geometry, geometry, *, timeout):
    with _decoded_pixels(source, frame_map, source_geometry, geometry, timeout=timeout) as raw:
        yield raw


@contextmanager
def decoded_rgb(source, frame_map, source_geometry, geometry, *, timeout, every=1):
    with _decoded_pixels(
        source,
        frame_map,
        source_geometry,
        geometry,
        timeout=timeout,
        pixel_format="rgb24",
        every=every,
    ) as raw:
        yield raw


def decode_measurements(
    source: Path,
    frame_map: FrameMap,
    source_geometry: tuple[int, int],
    geometry: tuple[int, int],
    settings: QualitySettings,
    *,
    timeout: float,
) -> list[dict]:
    width, height = geometry
    if len(range(0, len(frame_map.frames), settings.every)) > MAX_SAMPLES:
        raise ValueError("Analysis exceeds 10000 sample limit; increase --every")
    with decoded_gray(source, frame_map, source_geometry, geometry, timeout=timeout) as raw:
        observations = []
        for index in range(0, len(frame_map.frames), settings.every):
            raw.seek(index * width * height)
            measurements = measure_gray(raw.read(width * height), width, height, settings)
            observations.append(
                {
                    "frame_index": index,
                    "pts": frame_map.frames[index].pts,
                    "metrics": measurements,
                }
            )
        return observations


def analysis_tools() -> dict[str, str]:
    """Keep full build configuration in the key, not just a release label."""
    return {
        name: subprocess.check_output([name, "-version"], text=True, timeout=10)
        for name in ("ffmpeg", "ffprobe")
    }
