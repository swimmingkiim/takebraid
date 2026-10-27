import json
import shutil
import subprocess
from fractions import Fraction

import pytest

from takebraid.application.ingest import ingest
from takebraid.application.motion import observe_motion
from takebraid.cli import main
from takebraid.domain.motion import MotionSettings
from tools.motion_fixtures import sequence

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
        reason="requires media tools",
    ),
]


def make_source(tmp_path, kind, *, offset="0", vfr=False, fps="25"):
    raw = tmp_path / "motion.gray"
    raw.write_bytes(b"".join(sequence(kind)))
    mov = vfr or fps != "25"
    source = tmp_path / ("motion.mov" if mov else "motion.mkv")
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-copyts",
        "-itsoffset",
        offset,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-s",
        "96x64",
        "-framerate",
        fps,
        "-i",
        str(raw),
    ]
    if vfr:
        command += ["-vf", "select=not(eq(n\\,2))"]
    command += ["-fps_mode", "passthrough", "-c:v", "mpeg4" if mov else "ffv1"]
    if mov:
        command += ["-q:v", "2"]
    command += ["-avoid_negative_ts", "disabled", str(source)]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    return source


@pytest.mark.parametrize(
    "kind,translations",
    [
        ("static", [0, 0, 0]),
        ("pan", [1, 1, 1]),
        ("jitter", [2, -2, 2]),
        ("subject", [0, 0, 0]),
        ("camera-subject", [1, 1, 1]),
        ("flat", None),
        ("periodic", None),
        ("occlusion", None),
        ("boundary", None),
    ],
)
def test_encoded_motion_cases_have_known_displacements_or_unknown(tmp_path, kind, translations):
    source = make_source(tmp_path, kind)
    original = source.read_bytes()
    asset = ingest(source, tmp_path / "project")
    path, status = observe_motion(asset, 0)
    document = json.loads(path.read_text())
    if translations is None:
        assert status == "unknown"
        assert all(pair["translation"] is None for pair in document["pairs"])
        assert main(["motion", str(asset), "--stream", "0"]) == 2
    else:
        assert status == "observed"
        assert [pair["translation"] for pair in document["pairs"]] == [
            [dx, 0] for dx in translations
        ]
        assert document["model_role"] == "dominant_image_translation"
        if kind == "jitter":
            assert document["path"][1]["previous_sample_residual"][0] == {
                "numerator": 2,
                "denominator": 1,
            }
    assert source.read_bytes() == original
    assert observe_motion(asset, 0)[0] == path


def test_background_region_restricts_large_foreground_in_real_decode(tmp_path):
    asset = ingest(make_source(tmp_path, "majority-subject"), tmp_path / "project")
    path, status = observe_motion(asset, 0, MotionSettings(background=(64, 0, 32, 64)))
    assert status == "observed"
    document = json.loads(path.read_text())
    assert document["model_role"] == "declared_background_translation"
    assert all(pair["translation"] == [0, 0] for pair in document["pairs"])


@pytest.mark.parametrize(
    "offset,vfr,fps,expected_pts,translations",
    [
        (
            "-0.08",
            False,
            "25",
            [Fraction(-2, 25), Fraction(-1, 25), Fraction(0), Fraction(1, 25)],
            [1, 1, 1],
        ),
        ("2", True, "25", [Fraction(2), Fraction(51, 25), Fraction(53, 25)], [1, 2]),
        ("0", False, "30000/1001", [Fraction(i * 1001, 30000) for i in range(4)], [1, 1, 1]),
    ],
)
def test_motion_uses_exact_signed_vfr_fractional_source_clock(
    tmp_path, offset, vfr, fps, expected_pts, translations
):
    asset = ingest(
        make_source(tmp_path, "pan", offset=offset, vfr=vfr, fps=fps), tmp_path / "project"
    )
    path, status = observe_motion(asset, 0)
    assert status == "observed"
    document = json.loads(path.read_text())
    raw_clock = document["inputs"]["time_base"]
    clock = Fraction(raw_clock["numerator"], raw_clock["denominator"])
    assert [p["from_pts"] * clock for p in document["pairs"]] == expected_pts[:-1]
    assert [p["to_pts"] * clock for p in document["pairs"]] == expected_pts[1:]
    assert [p["translation"] for p in document["pairs"]] == [[dx, 0] for dx in translations]
    assert all(
        p["previous_sample_residual"] == [{"numerator": 0, "denominator": 1}] * 2
        for p in document["path"][1:]
    )
