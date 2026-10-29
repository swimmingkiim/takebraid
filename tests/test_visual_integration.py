import json
import shutil
import subprocess
from fractions import Fraction as F

import pytest

from takebraid.application.ingest import ingest
from takebraid.application.visual import compare_visual, observe_visual
from takebraid.cli import main
from tools.media_validation.fixtures import generate_case
from tools.media_validation.runner import load_cases

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requires media tools"
    ),
]


def asset_with_frames(tmp_path, name, values, width=32, height=32):
    # Coarse structures survive the 8x8 grid; high-frequency texture is deliberately not the oracle.
    raw = tmp_path / f"{name}.gray"
    raw.write_bytes(
        b"".join(
            bytes(values[(x // 4 + y // 4) % 2] for y in range(height) for x in range(width))
            for _ in range(3)
        )
    )
    source = tmp_path / f"{name}.mkv"
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
            f"{width}x{height}",
            "-framerate",
            "25",
            "-i",
            str(raw),
            "-metadata",
            f"title={name}",
            "-c:v",
            "ffv1",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return ingest(source, tmp_path / f"project-{name}")


def test_actual_duplicate_pattern_matches_cache_force_and_cli_contract(tmp_path, capsys):
    a = asset_with_frames(tmp_path, "a", (16, 240))
    b = asset_with_frames(tmp_path, "b", (16, 240))
    pa, status = observe_visual(a, 0, size=32, every=1)
    pb, _ = observe_visual(b, 0, size=32, every=1)
    assert status == "observed"
    assert observe_visual(a, 0, size=32, every=1)[0] == pa
    forced, _ = observe_visual(a, 0, size=32, every=1, force=True)
    assert forced != pa and forced.read_bytes() == pa.read_bytes()
    options = {"max_distance": F(0), "min_variance": F(1, 100), "limit": 4}
    output = tmp_path / "comparisons"
    report = compare_visual([(a, pa), (b, pb)], output, **options)
    record = json.loads(report.read_text())
    assert record["matching_pairs"] == 9 and record["truncated_pairs"] == 5
    assert len(record["matches"]) == 4
    assert all(r["distance"] == {"numerator": 0, "denominator": 1} for r in record["matches"])
    assert record["semantic_equivalence_validated"] is False
    assert record["automatic_exclusion_validated"] is False
    assert compare_visual([(b, pb), (a, pa)], output, **options) == report
    forced_report = compare_visual([(a, pa), (b, pb)], output, force=True, **options)
    assert forced_report != report and forced_report.read_bytes() == report.read_bytes()
    assert (
        main(
            [
                "visual",
                "compare",
                "--input",
                str(a),
                str(pa),
                "--input",
                str(b),
                str(pb),
                "--output",
                str(tmp_path / "cli"),
                "--max-distance",
                "0",
                "--min-variance",
                "1/100",
                "--limit",
                "4",
            ]
        )
        == 0
    )
    assert "matches.json" in capsys.readouterr().out
    data = json.loads(pa.read_text())
    data["observations"][0]["values"][0] = {"numerator": 0, "denominator": 1}
    pa.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="receipt"):
        compare_visual([(a, pa), (b, pb)], output, **options)


def test_flat_reversed_and_repeated_content_are_not_silently_classified_as_duplicates(tmp_path):
    a = asset_with_frames(tmp_path, "normal", (16, 240))
    b = asset_with_frames(tmp_path, "reverse", (240, 16))
    c = asset_with_frames(tmp_path, "flat", (128, 128))
    sources = [(p, observe_visual(p, 0, size=32, every=1)[0]) for p in (a, b, c)]
    path = compare_visual(sources, tmp_path / "match", max_distance=F(0), min_variance=F(1, 100))
    report = json.loads(path.read_text())
    assert report["matching_pairs"] == 0
    assert sum(report["low_texture_samples"].values()) == 3
    with pytest.raises(ValueError, match="distinct"):
        compare_visual(
            [sources[0], sources[0]], tmp_path / "bad", max_distance=F(0), min_variance=F(1, 100)
        )


@pytest.mark.parametrize("case_id", ["negative-start", "vfr-hold"])
def test_visual_sample_clock_matches_independent_source_oracle(tmp_path, case_id):
    case = next(c for c in load_cases()["cases"] if c["id"] == case_id)
    source = generate_case(tmp_path, case, [])
    asset = ingest(source, tmp_path / "project")
    path, status = observe_visual(asset, 0, size=32, every=2)
    assert status == "observed"
    record = json.loads(path.read_text())
    raw_clock = record["inputs"]["time_base"]
    clock = F(raw_clock["numerator"], raw_clock["denominator"])
    assert [r["pts"] * clock for r in record["observations"]] == [
        F(p) for p in case["expected"]["source_pts"][::2]
    ]


def test_unknown_tiny_analysis_grid_is_preserved_and_cli_returns_two(tmp_path, capsys):
    asset = asset_with_frames(tmp_path, "tiny", (0, 255), width=32, height=128)
    assert main(["visual", "observe", str(asset), "--stream", "0", "--size", "16"]) == 2
    assert "unknown" in capsys.readouterr().err
    descriptor, status = observe_visual(asset, 0, size=16)
    record = json.loads(descriptor.read_text())
    assert status == "unknown" and record["observations"] == []
    assert "descriptor_grid_too_small" in record["reasons"]
