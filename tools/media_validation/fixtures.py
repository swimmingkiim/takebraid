"""Small visible-index patterns and precisely placed PCM impulses; no external media."""

import array
import json
import subprocess
import sys
import wave
from fractions import Fraction
from pathlib import Path

WIDTH, HEIGHT, COUNT = 64, 48, 8


def round_half_up(value: Fraction) -> int:
    # Fixture generator timing only; expectations are separately committed in cases.json.
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def write_indexed_inputs(folder: Path, fps: Fraction = Fraction(25), *, audio_frames: int = 8):
    raw, audio = folder / "indexed.gray", folder / "impulses.wav"
    segments = {
        0: "abcdef",
        1: "bc",
        2: "abdeg",
        3: "abcdg",
        4: "bcfg",
        5: "acdfg",
        6: "acdefg",
        7: "abc",
    }
    rectangles = {
        "a": (16, 6, 34, 9),
        "b": (31, 8, 34, 23),
        "c": (31, 23, 34, 38),
        "d": (16, 36, 34, 39),
        "e": (16, 23, 19, 38),
        "f": (16, 8, 19, 23),
        "g": (16, 21, 34, 24),
    }
    with raw.open("xb") as handle:
        for index in range(COUNT):
            pixels = bytearray([16 + index * 16]) * (WIDTH * HEIGHT)
            for segment in segments[index]:
                x0, y0, x1, y1 = rectangles[segment]
                for y in range(y0, y1):
                    pixels[y * WIDTH + x0 : y * WIDTH + x1] = b"\xff" * (x1 - x0)
            handle.write(pixels)
    samples = array.array("h", [0]) * round_half_up(Fraction(audio_frames * 48000, 1) / fps)
    for index in range(audio_frames):
        position = round_half_up(Fraction(index * 48000, 1) / fps) + 100
        if position < len(samples):
            samples[position] = 24000
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(audio), "wb") as handle:
        handle.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        handle.writeframes(samples.tobytes())
    return raw, audio


def command_run(command: list[str], log: list[list[str]]) -> bytes:
    log.append(command)
    result = subprocess.run(
        command, stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=30
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-4000:])
    return result.stdout


def decimal_offset(value: Fraction) -> str:
    # Selected offsets are exactly representable in decimal (0, +/-0.08, 2).
    if value.denominator not in {1, 5, 25}:
        raise ValueError("Fixture offsets must be exact multiples of 1/25 second")
    return f"{value.numerator * 100 // value.denominator / 100:.2f}"


def generate_case(folder: Path, case: dict, log: list[list[str]]) -> Path:
    source = case["source"]
    fps = Fraction(source["fps"])
    raw, audio = write_indexed_inputs(folder, fps, audio_frames=source["audio_frames"])
    destination = folder / f"source.{source['format']}"
    base = folder / "unrotated.mov" if source["rotation"] else destination
    offset = Fraction(source["offset"])
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-n",
        "-copyts",
        "-itsoffset",
        decimal_offset(offset),
        "-f",
        "rawvideo",
        "-pixel_format",
        "gray",
        "-video_size",
        "64x48",
        "-framerate",
        source["fps"],
        "-i",
        str(raw),
    ]
    if source["audio_frames"]:
        command += [
            "-itsoffset",
            decimal_offset(offset + Fraction(source["audio_delay"])),
            "-i",
            str(audio),
        ]
    filters = []
    if source["frame_ids"] != list(range(COUNT)):
        filters.append("select=" + "+".join(f"eq(n\\,{index})" for index in source["frame_ids"]))
    if source["sar"] != "1/1":
        filters.append(f"setsar={source['sar']}")
    if filters:
        command += ["-vf", ",".join(filters)]
    command += ["-fps_mode", "passthrough", "-c:v", source["codec"]]
    if source["codec"] == "mpeg4":
        command += ["-bf", str(source["b_frames"]), "-q:v", "2"]
    if source["audio_frames"]:
        command += ["-c:a", "pcm_s16le"]
    command += ["-avoid_negative_ts", "disabled", str(base)]
    command_run(command, log)
    if source["rotation"]:
        command_run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-copyts",
                "-display_rotation:v:0",
                str(source["rotation"]),
                "-i",
                str(base),
                "-c",
                "copy",
                "-avoid_negative_ts",
                "disabled",
                str(destination),
            ],
            log,
        )
    return destination


def raw_probe(path: Path, log: list[list[str]]) -> dict:
    return json.loads(
        command_run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)], log)
    )


def decode_gray(path: Path, log: list[list[str]]) -> bytes:
    return command_run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-noautorotate",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        log,
    )


def decode_audio(path: Path, log: list[list[str]]) -> array.array:
    data = command_run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-ac",
            "1",
            "-",
        ],
        log,
    )
    values = array.array("h")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    return values
