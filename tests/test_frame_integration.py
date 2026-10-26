import json
import shutil
import subprocess
from fractions import Fraction

import pytest

from takebraid.application.ingest import ingest
from takebraid.application.scan import scan_asset

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
        reason="requires media tools",
    ),
]


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("cfr", [0, 1, 2, 3, 4, 5, 6]),
        ("vfr", [0, 2, 3, 5, 6]),
        ("offset", [50, 51, 52, 53, 54, 55, 56]),
        ("bframes", [0, 1, 2, 3, 4, 5, 6]),
    ],
)
def test_decoded_pts_match_synthetic_source_schedule(tmp_path, mode, expected):
    source = tmp_path / f"{mode}.mov"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=64x48:r=25:d=0.28",
    ]
    if mode == "vfr":
        command += ["-vf", r"select=not(eq(n\,1)+eq(n\,4))", "-fps_mode", "vfr"]
    elif mode == "offset":
        command += ["-vf", "setpts=PTS+2/TB", "-fps_mode", "vfr"]
    command += ["-c:v", "mpeg4", "-bf", "2" if mode == "bframes" else "0", str(source)]
    subprocess.run(command, capture_output=True, check=True, timeout=30)
    asset = ingest(source, tmp_path / "project")
    output, status = scan_asset(asset, 0)
    result = json.loads(output.read_text())
    assert status == "ready", result["issues"]
    clock = result["frame_map"]["time_base"]
    tick = Fraction(clock["numerator"], clock["denominator"])
    assert [frame["pts"] * tick for frame in result["frame_map"]["frames"]] == [
        Fraction(frame, 25) for frame in expected
    ]
    assert result["presentation_end_pts"] * tick == Fraction(expected[-1] + 1, 25)
    assert result["cadence"] == (
        "variable_pts_intervals" if mode == "vfr" else "uniform_pts_intervals"
    )
