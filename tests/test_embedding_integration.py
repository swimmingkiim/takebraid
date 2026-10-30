import json
import math
import shutil
import subprocess
from dataclasses import replace
from fractions import Fraction

import pytest

from takebraid.adapters.media.quality import decoded_rgb
from takebraid.adapters.models.preprocessing import CROP_RESIZE
from takebraid.adapters.projects import asset_source
from takebraid.adapters.records import load_asset, load_frame_map
from takebraid.application.embeddings import observe_embeddings
from takebraid.application.ingest import ingest
from takebraid.application.scan import scan_asset
from takebraid.cli import main
from tools.embedding_fixture import generate
from tools.media_validation.fixtures import generate_case
from tools.media_validation.runner import load_cases

pytestmark = [
    pytest.mark.onnx,
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requires media tools"
    ),
]


@pytest.fixture
def model(tmp_path):
    pytest.importorskip("onnx")
    from importlib.util import find_spec

    if find_spec("onnxruntime") is None:
        pytest.skip("optional ONNX runtime unavailable")
    return generate(tmp_path / "model")


def colored_asset(tmp_path):
    raw = tmp_path / "rgb.raw"
    raw.write_bytes(bytes([64, 128, 192]) * 16 * 16 + bytes(16 * 16 * 3))
    source = tmp_path / "colors.nut"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "16x16",
            "-framerate",
            "25",
            "-i",
            str(raw),
            "-c:v",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return ingest(source, tmp_path / "project")


def test_rgb_encoder_exact_clock_unknown_output_cache_force_and_cli(tmp_path, model, capsys):
    asset = colored_asset(tmp_path)
    path, status = observe_embeddings(asset, 0, model, every=1)
    record = json.loads(path.read_text())
    assert status == "partial"
    clock = record["inputs"]["time_base"]
    scale = Fraction(clock["numerator"], clock["denominator"])
    assert [row["pts"] * scale for row in record["observations"]] == [0, Fraction(1, 25)]
    first, second = record["observations"]
    norm = math.hypot(64, 128, 192)
    assert first["values"] == pytest.approx([v / norm for v in (64, 128, 192)], abs=1e-6)
    assert second["values"] is None and second["reason"] == "zero_model_output"
    assert observe_embeddings(asset, 0, model, every=1)[0] == path
    forced, _ = observe_embeddings(asset, 0, model, every=1, force=True)
    assert forced != path and forced.read_bytes() == path.read_bytes()
    assert main(["embed", str(asset), "--stream", "0", "--model", str(model), "--every", "1"]) == 2
    assert "partial" in capsys.readouterr().err
    # A structurally plausible edited vector is still rejected by the terminal checksum.
    data = json.loads(forced.read_text())
    data["observations"][0]["values"] = [1.0, 0.0, 0.0]
    forced.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="checksum"):
        observe_embeddings(asset, 0, model, every=1)


@pytest.mark.parametrize("case_id", ["negative-start", "vfr-hold"])
@pytest.mark.parametrize("resize", ["stretch-area", CROP_RESIZE])
def test_onnx_embeddings_keep_independent_source_pts_oracle(tmp_path, model, case_id, resize):
    if resize == CROP_RESIZE:
        pytest.importorskip("PIL")
        spec = json.loads(model.read_text())
        spec["input"].update(resize=CROP_RESIZE, resize_short_edge=20)
        model.write_text(json.dumps(spec))
    case = next(c for c in load_cases()["cases"] if c["id"] == case_id)
    source = generate_case(tmp_path, case, [])
    asset = ingest(source, tmp_path / "project")
    path, _ = observe_embeddings(asset, 0, model, every=2)
    record = json.loads(path.read_text())
    clock = record["inputs"]["time_base"]
    scale = Fraction(clock["numerator"], clock["denominator"])
    assert [row["pts"] * scale for row in record["observations"]] == [
        Fraction(p) for p in case["expected"]["source_pts"][::2]
    ]


def test_nonfinite_graph_and_manifest_preprocessing_changes_have_explicit_coverage(tmp_path, model):
    asset = colored_asset(tmp_path)
    invalid = generate(tmp_path / "nonfinite", mode="nonfinite")
    path, status = observe_embeddings(asset, 0, invalid, every=1)
    assert status == "partial"
    assert all(
        row["reason"] == "nonfinite_model_output"
        for row in json.loads(path.read_text())["observations"]
    )
    old, _ = observe_embeddings(asset, 0, model, every=1)
    spec = json.loads(model.read_text())
    spec["input"]["mean"] = [0.1, 0.1, 0.1]
    model.write_text(json.dumps(spec))
    new, _ = observe_embeddings(asset, 0, model, every=1)
    assert new != old
    assert (
        json.loads(new.read_text())["inputs"]["settings"]["model_manifest_sha256"]
        != json.loads(old.read_text())["inputs"]["settings"]["model_manifest_sha256"]
    )


@pytest.fixture
def wide_asset(tmp_path):
    raw = tmp_path / "borders.rgb"
    # The center 16 columns are green; a stretch would mix in the red borders.
    raw.write_bytes(
        (bytes([255, 0, 0]) * 32 + bytes([0, 255, 0]) * 16 + bytes([255, 0, 0]) * 32) * 16 * 2
    )
    source = tmp_path / "borders.nut"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "80x16",
            "-framerate",
            "25",
            "-i",
            str(raw),
            "-c:v",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return ingest(source, tmp_path / "project")


def test_crop_decodes_original_geometry_and_removes_borders_before_inference(wide_asset, model):
    pytest.importorskip("PIL")
    legacy, _ = observe_embeddings(wide_asset, 0, model, every=1)
    spec = json.loads(model.read_text())
    spec["input"].update(resize=CROP_RESIZE, resize_short_edge=16)
    model.write_text(json.dumps(spec))
    crop, status = observe_embeddings(wide_asset, 0, model, every=1)
    record = json.loads(crop.read_text())
    assert status == "observed" and crop != legacy
    assert record["inputs"]["recipe"] == "local-onnx-image-embedding/2"
    assert record["inputs"]["settings"]["runtime"]["pillow"]
    assert record["analysis_geometry"] == [16, 16]
    assert record["inputs"]["source_geometry"] == [80, 16]
    assert [r["pts"] for r in record["observations"]] == [
        r["pts"] for r in json.loads(legacy.read_text())["observations"]
    ]
    for row in record["observations"]:
        assert row["values"] == pytest.approx([0.0, 1.0, 0.0], abs=1e-6)
    assert json.loads(legacy.read_text())["observations"][0]["values"][0] > 0.5
    assert observe_embeddings(wide_asset, 0, model, every=1)[0] == crop


def test_crop_rgb_budget_counts_original_pixels_before_decode(wide_asset, model, monkeypatch):
    pytest.importorskip("PIL")
    spec = json.loads(model.read_text())
    spec["input"].update(resize=CROP_RESIZE, resize_short_edge=20)
    model.write_text(json.dumps(spec))
    # 2 * 16 * 16 * 3 fits; 2 * 80 * 16 * 3 original pixels do not.
    monkeypatch.setattr("takebraid.application.embeddings.MAX_DECODE_BYTES", 2000)
    monkeypatch.setattr("takebraid.application.analysis.MAX_DECODE_BYTES", 1)
    monkeypatch.setattr(
        "takebraid.application.embeddings.decoded_rgb",
        lambda *args, **kwargs: pytest.fail("Over-budget source must not decode"),
    )
    path, status = observe_embeddings(wide_asset, 0, model, every=1)
    record = json.loads(path.read_text())
    assert status == "unknown" and record["observations"] == []
    assert "rgb_decoded_byte_budget_exceeded" in record["reasons"]
    assert "decoded_byte_budget_exceeded" not in record["reasons"]


def test_sparse_rgb_spool_still_checks_unsampled_source_pts(wide_asset):
    _, source = asset_source(wide_asset, load_asset(wide_asset))
    map_path, _ = scan_asset(wide_asset, 0)
    frame_map = load_frame_map(map_path)
    with decoded_rgb(source, frame_map, (80, 16), (80, 16), timeout=30, every=2) as raw:
        assert raw.seek(0, 2) == 80 * 16 * 3
    # Index 1 is not emitted, but its source PTS must still be checked before selection.
    bad = replace(frame_map, frames=(frame_map.frames[0], replace(frame_map.frames[1], pts=999)))
    with pytest.raises(ValueError, match="PTS/geometry"):
        with decoded_rgb(source, bad, (80, 16), (80, 16), timeout=30, every=2):
            pytest.fail("Unverified unsampled source PTS must not yield pixels")
