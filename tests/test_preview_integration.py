import array
import hashlib
import json
import shutil
import subprocess
import sys
import wave
from fractions import Fraction

import pytest

from takebraid.adapters.media.probe import ProbeError
from takebraid.application.ingest import ingest
from takebraid.application.preview import create_plan, render_plan
from takebraid.cli import main

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requires media tools"
    ),
]


@pytest.fixture
def indexed_source(tmp_path):
    width, height, count = 64, 48, 8
    raw = tmp_path / "indexed.gray"
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
    with raw.open("wb") as handle:
        for index in range(count):
            pixels = bytearray([16 + index * 16]) * (width * height)
            for segment in segments[index]:
                x0, y0, x1, y1 = rectangles[segment]
                for y in range(y0, y1):
                    pixels[y * width + x0 : y * width + x1] = b"\xff" * (x1 - x0)
            handle.write(pixels)
    audio = tmp_path / "impulses.wav"
    samples = array.array("h", [0]) * (count * 1920)
    for index in range(count):
        samples[index * 1920 + 100] = 24000
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(audio), "wb") as output:
        output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())
    return raw, audio


def make_indexed_media(tmp_path, indexed_source, *, delay=False):
    raw, audio = indexed_source
    source = tmp_path / "indexed source ; sample.mkv"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-f",
        "rawvideo",
        "-pixel_format",
        "gray",
        "-video_size",
        "64x48",
        "-framerate",
        "25",
        "-i",
        str(raw),
    ]
    if delay:
        command += ["-itsoffset", "0.08"]
    command += ["-i", str(audio), "-c:v", "ffv1", "-c:a", "pcm_s16le", str(source)]
    subprocess.run(command, capture_output=True, check=True, timeout=30)
    return source


def decode_gray(path):
    return subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
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
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout


def decode_audio(path):
    data = subprocess.run(
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
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    values = array.array("h")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    return values


@pytest.mark.parametrize("delay", [False, True])
def test_frame_identity_and_impulse_alignment_across_multiple_cuts(tmp_path, indexed_source, delay):
    source = make_indexed_media(tmp_path, indexed_source, delay=delay)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    root = tmp_path / "project"
    asset = ingest(source, root)
    cuts = ((0, 2), (2, 5)) if delay else ((3, 5), (0, 2), (5, 6))
    expected = [0, 1, 2, 3, 4] if delay else [3, 4, 0, 1, 5]
    plan = create_plan(asset, 0, cuts, Fraction(25), "source", 1)
    output = render_plan(root, plan)
    pixels = decode_gray(output)
    originals = decode_gray(source)
    for index, source_index in enumerate(expected):
        assert abs(pixels[index * 64 * 48] - originals[source_index * 64 * 48]) <= 5
    samples = decode_audio(output)
    peaks = [i for i, value in enumerate(samples) if abs(value) > 5000]
    assert peaks == [i * 1920 + 100 for i in range(2 if delay else 0, 5)]
    assert len(samples) == 5 * 1920
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert render_plan(root, plan) == output
    repeated = render_plan(root, plan, force=True)
    assert repeated != output and output.exists()


@pytest.mark.parametrize("mode", ["ntsc", "vfr", "offset", "mute", "aac44100"])
def test_preview_clocks_for_fractional_vfr_and_nonzero_sources(tmp_path, mode):
    source = tmp_path / "source.mov"
    fps = "30000/1001" if mode == "ntsc" else "25"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s=64x48:r={fps}:d=0.4",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate={44100 if mode == 'aac44100' else 48000}:duration=0.4",
    ]
    if mode == "vfr":
        command += ["-vf", r"select=not(eq(n\,1)+eq(n\,4))", "-fps_mode", "vfr"]
    elif mode == "offset":
        command += ["-vf", "setpts=PTS+2/TB", "-af", "asetpts=PTS+2/TB", "-fps_mode", "vfr"]
    command += ["-c:v", "mpeg4", "-c:a", "aac" if mode == "aac44100" else "pcm_s16le", str(source)]
    subprocess.run(command, capture_output=True, check=True, timeout=30)
    root = tmp_path / "project"
    asset = ingest(source, root)
    policy = "mute" if mode == "mute" else "source"
    plan = create_plan(
        asset, 0, ((0, 1), (2, 5)), Fraction(fps), policy, 1 if policy == "source" else None
    )
    output = render_plan(root, plan)
    verification = json.loads((output.parent / "verification.json").read_text())
    assert verification["video_frames"] == (6 if mode == "vfr" else 4)
    assert (verification["audio_samples"] == 0) == (mode == "mute")


def test_tampered_plan_source_and_failed_renders_never_reuse_or_clobber(
    tmp_path, indexed_source, monkeypatch
):
    source = make_indexed_media(tmp_path, indexed_source)
    root = tmp_path / "project"
    asset = ingest(source, root)
    plan = create_plan(asset, 0, ((0, 3),), Fraction(25), "mute", None)
    first = render_plan(root, plan)
    original = first.read_bytes()

    def failure(*args, **kwargs):
        raise ProbeError("simulated rendering failure")

    monkeypatch.setattr("takebraid.application.preview.render_preview", failure)
    with pytest.raises(ProbeError):
        render_plan(root, plan, force=True)
    assert first.read_bytes() == original
    assert render_plan(root, plan) == first
    document = json.loads(plan.read_text())
    document["timeline"]["cuts"][0]["in_pts"] += 1
    plan.write_text(json.dumps(document))
    assert main(["render", str(plan), "--project", str(root)]) == 1
    source.write_bytes(b"changed source")
    with pytest.raises(ValueError):
        create_plan(asset, 0, ((0, 1),), Fraction(25), "mute", None)


def test_plan_change_during_render_never_certifies_the_old_snapshot(
    tmp_path, indexed_source, monkeypatch
):
    source = make_indexed_media(tmp_path, indexed_source)
    root = tmp_path / "project"
    asset = ingest(source, root)
    plan = create_plan(asset, 0, ((0, 2),), Fraction(25), "mute", None)
    from takebraid.adapters.media.render import render_preview

    def changing_plan(*args, **kwargs):
        document = json.loads(plan.read_text())
        document["editor_note"] = "changed while rendering"
        plan.write_text(json.dumps(document))
        return render_preview(*args, **kwargs)

    monkeypatch.setattr("takebraid.application.preview.render_preview", changing_plan)
    with pytest.raises(ValueError, match="timeline changed"):
        render_plan(root, plan)
    receipts = [
        json.loads(path.read_text()) for path in root.glob("stages/*/attempts/*/receipt.json")
    ]
    assert any(
        r["status"] == "failed" and r["inputs"]["recipe"] == "manual-preview/1" for r in receipts
    )


def test_vfr_preview_holds_the_active_source_picture_at_output_grid(tmp_path, indexed_source):
    raw, _ = indexed_source
    source = tmp_path / "indexed-vfr.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pixel_format",
            "gray",
            "-video_size",
            "64x48",
            "-framerate",
            "25",
            "-i",
            str(raw),
            "-vf",
            r"select=not(eq(n\,1)+eq(n\,4))",
            "-fps_mode",
            "vfr",
            "-c:v",
            "mpeg4",
            str(source),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    root = tmp_path / "project"
    asset = ingest(source, root)
    plan = create_plan(asset, 0, ((0, 3),), Fraction(25), "mute", None)
    output = render_plan(root, plan)
    actual, original = decode_gray(output), decode_gray(source)
    # Original pictures at 0,80,120 ms; the exclusive next boundary is 200 ms.
    # Output samples 0,40,80,120,160 ms, holding the final selected picture.
    assert len(actual) == 5 * 64 * 48
    for index, source_index in enumerate((0, 0, 1, 2, 2)):
        assert abs(actual[index * 64 * 48] - original[source_index * 64 * 48]) <= 5


def test_cli_cancellation_records_cancelled_render_attempt(tmp_path, indexed_source, monkeypatch):
    source = make_indexed_media(tmp_path, indexed_source)
    root = tmp_path / "project"
    asset = ingest(source, root)
    plan = create_plan(asset, 0, ((0, 2),), Fraction(25), "mute", None)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("takebraid.application.preview.render_preview", interrupt)
    assert main(["render", str(plan), "--project", str(root)]) == 130
    receipts = [
        json.loads(path.read_text()) for path in root.glob("stages/*/attempts/*/receipt.json")
    ]
    assert any(
        r["status"] == "cancelled" and r["inputs"]["recipe"] == "manual-preview/1" for r in receipts
    )
