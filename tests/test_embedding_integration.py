import json
import math
import shutil
import subprocess
from fractions import Fraction

import pytest

from takebraid.application.embeddings import observe_embeddings
from takebraid.application.ingest import ingest
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
def test_onnx_embeddings_keep_independent_source_pts_oracle(tmp_path, model, case_id):
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
