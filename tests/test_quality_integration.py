import json
import shutil
import subprocess
from fractions import Fraction

import pytest

from takebraid.application.ingest import ingest
from takebraid.application.quality import observe_quality
from takebraid.domain.quality import QualitySettings
from tools.media_validation.fixtures import generate_case
from tools.media_validation.runner import load_cases

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
        reason="requires media tools",
    ),
]


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


@pytest.fixture
def signals(tmp_path):
    width, height = 64, 48
    sharp = bytes(255 if (x // 4 + y // 4) % 2 else 0 for y in range(height) for x in range(width))
    blurred = bytes(
        sum(
            sharp[min(height - 1, max(0, y + dy)) * width + min(width - 1, max(0, x + dx))]
            for dy in range(-2, 3)
            for dx in range(-2, 3)
        )
        // 25
        for y in range(height)
        for x in range(width)
    )
    raw = tmp_path / "patterns.gray"
    raw.write_bytes(
        sharp
        + blurred
        + bytes(width * height)
        + bytes([255]) * width * height
        + bytes([128]) * width * height
    )
    source = tmp_path / "signals.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            "64x48",
            "-r",
            "25",
            "-i",
            str(raw),
            "-c:v",
            "ffv1",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return ingest(source, tmp_path / "project")


def test_real_decode_measures_blur_and_brightness_in_source_clock(signals):
    path, status = observe_quality(signals, 0)
    assert status == "observed"
    rows = json.loads(path.read_text())["observations"]
    assert [r["pts"] for r in rows] == [0, 40, 80, 120, 160]
    metrics = [r["metrics"] for r in rows]
    assert ratio(metrics[0]["laplacian_variance"]) > ratio(metrics[1]["laplacian_variance"]) * 5
    assert ratio(metrics[2]["dark_fraction"]) == 1
    assert ratio(metrics[3]["bright_fraction"]) == 1
    assert ratio(metrics[4]["mean_luma"]) == Fraction(128, 255)
    assert observe_quality(signals, 0)[0] == path
    roi, _ = observe_quality(signals, 0, QualitySettings(roi=(2, 2, 16, 16), every=2))
    document = json.loads(roi.read_text())
    assert document["roi"] == [2, 2, 16, 16]
    assert [r["frame_index"] for r in document["observations"]] == [0, 2, 4]


@pytest.mark.parametrize("case_id", ["negative-start", "positive-start", "vfr-hold", "ntsc"])
def test_sample_coordinates_match_independent_source_oracle(tmp_path, case_id):
    case = next(c for c in load_cases()["cases"] if c["id"] == case_id)
    source = generate_case(tmp_path, case, [])
    asset = ingest(source, tmp_path / "project")
    path, status = observe_quality(asset, 0, QualitySettings(every=2, size=32))
    assert status == "observed"
    document = json.loads(path.read_text())
    clock = ratio(document["inputs"]["time_base"])
    assert [r["pts"] * clock for r in document["observations"]] == [
        Fraction(p) for p in case["expected"]["source_pts"][::2]
    ]
    assert max(document["analysis_geometry"]) == 32
