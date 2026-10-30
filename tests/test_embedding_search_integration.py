import json
import shutil
import subprocess
from importlib.util import find_spec
from unittest.mock import patch

import pytest

from takebraid.adapters.models.preprocessing import CROP_RESIZE
from takebraid.application.embedding_search import search_embeddings
from takebraid.application.embeddings import observe_embeddings
from takebraid.application.ingest import ingest
from takebraid.cli import main
from tools.embedding_fixture import generate

pytestmark = [
    pytest.mark.onnx,
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requires media tools"
    ),
]


def colored_source(tmp_path, name, colors):
    raw = tmp_path / f"{name}.rgb"
    raw.write_bytes(b"".join(bytes(c) * 16 * 16 for c in colors))
    source = tmp_path / f"{name}.nut"
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
    return ingest(source, tmp_path / f"project-{name}"), source


@pytest.fixture
def recorded_pair(tmp_path):
    pytest.importorskip("onnx")
    if find_spec("onnxruntime") is None:
        pytest.skip("optional ONNX runtime unavailable")
    model = generate(tmp_path / "model")
    a, raw_a = colored_source(tmp_path, "a", [(255, 0, 0), (0, 255, 0), (0, 0, 0)])
    b, raw_b = colored_source(tmp_path, "b", [(0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 0, 0)])
    ea, _ = observe_embeddings(a, 0, model, every=1)
    eb, _ = observe_embeddings(b, 0, model, every=1)
    return [(a, ea), (b, eb)], model, [raw_a, raw_b]


def test_actual_encoder_records_search_without_models_or_runtime_then_preserve_cache_history(
    tmp_path, recorded_pair, capsys
):
    sources, model, _ = recorded_pair
    model.parent.rename(tmp_path / "archived-model")
    # Model initialization and optional imports are forbidden during saved-vector search.
    with patch(
        "takebraid.adapters.models.onnx.importlib.import_module",
        side_effect=AssertionError("Unexpected model/runtime import"),
    ):
        output = tmp_path / "search"
        result = search_embeddings(sources, output, min_cosine=1.0)
        record = json.loads(result.read_text())
        assert record["possible_pairs"] == 12
        assert record["evaluated_pairs"] == 6 and record["unknown_pairs"] == 6
        assert record["matching_pairs"] == 2
        assert record["semantic_accuracy_validated"] is False
        assert sum(record["unknown_samples"].values()) == 2
        identities = [json.loads(p.read_text())["asset_id"] for p, _ in sources]
        actual = {
            frozenset((m[side]["asset_id"], m[side]["frame_index"]) for side in ("left", "right"))
            for m in record["matches"]
        }
        assert actual == {
            frozenset(((identities[0], 0), (identities[1], 1))),
            frozenset(((identities[0], 1), (identities[1], 0))),
        }
        assert search_embeddings(list(reversed(sources)), output, min_cosine=1.0) == result
        forced = search_embeddings(sources, output, min_cosine=1.0, force=True)
        assert forced != result and forced.read_bytes() == result.read_bytes()
        limited = search_embeddings(sources, output, min_cosine=1.0, limit=1)
        assert json.loads(limited.read_text())["truncated_pairs"] == 1
        assert (
            main(
                [
                    "embedding-search",
                    "--input",
                    str(sources[0][0]),
                    str(sources[0][1]),
                    "--input",
                    str(sources[1][0]),
                    str(sources[1][1]),
                    "--min-cosine",
                    "1",
                    "--output",
                    str(tmp_path / "cli"),
                ]
            )
            == 0
        )
        assert "embedding-matches.json" in capsys.readouterr().out


def test_incompatible_preprocessing_and_duplicate_assets_are_rejected(tmp_path, recorded_pair):
    sources, model, _ = recorded_pair
    with pytest.raises(ValueError, match="distinct"):
        search_embeddings([sources[0], sources[0]], tmp_path / "same", min_cosine=0.5)
    spec = json.loads(model.read_text())
    spec["input"]["mean"] = [0.1, 0.1, 0.1]
    model.write_text(json.dumps(spec))
    other, _ = observe_embeddings(sources[1][0], 0, model, every=1)
    with pytest.raises(ValueError, match="Incompatible embedding spaces"):
        search_embeddings([sources[0], (sources[1][0], other)], tmp_path / "mixed", min_cosine=0.5)
    assert not (tmp_path / "mixed").exists()


def test_changed_receipts_and_changed_originals_cannot_be_searched(tmp_path, recorded_pair):
    sources, _, raws = recorded_pair
    artifact = sources[0][1]
    before = artifact.read_bytes()
    record = json.loads(before)
    record["observations"][0]["values"] = [0.0, 1.0, 0.0]
    artifact.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="receipt"):
        search_embeddings(sources, tmp_path / "tampered", min_cosine=0.0)
    artifact.write_bytes(before)
    raws[0].write_bytes(raws[0].read_bytes() + b"changed original")
    with pytest.raises(ValueError):
        search_embeddings(sources, tmp_path / "changed", min_cosine=0.0)
    assert not (tmp_path / "changed").exists()


def test_search_preserves_vfr_and_negative_source_positions(tmp_path, recorded_pair):
    from fractions import Fraction

    from tools.media_validation.fixtures import generate_case
    from tools.media_validation.runner import load_cases

    _, model, _ = recorded_pair
    sources, clocks, points = [], {}, {}
    for case_id in ("negative-start", "vfr-hold"):
        folder = tmp_path / case_id
        folder.mkdir()
        case = next(c for c in load_cases()["cases"] if c["id"] == case_id)
        source = generate_case(folder, case, [])
        asset = ingest(source, folder / "project")
        artifact, _ = observe_embeddings(asset, 0, model, every=1)
        record = json.loads(artifact.read_text())
        asset_id = record["inputs"]["asset_id"]
        clock = record["inputs"]["time_base"]
        clocks[asset_id] = Fraction(clock["numerator"], clock["denominator"])
        points[asset_id] = [Fraction(p) for p in case["expected"]["source_pts"]]
        sources.append((asset, artifact))
    result = json.loads(
        search_embeddings(
            sources, tmp_path / "clock-search", min_cosine=-1.0, limit=1000
        ).read_text()
    )
    assert result["matches"]
    for match in result["matches"]:
        for side in ("left", "right"):
            point = match[side]
            assert (
                point["pts"] * clocks[point["asset_id"]]
                == points[point["asset_id"]][point["frame_index"]]
            )


def test_crop_records_replay_without_pillow_or_runtime_and_reject_legacy_space(
    tmp_path, recorded_pair
):
    pytest.importorskip("PIL")
    sources, model, _ = recorded_pair
    spec = json.loads(model.read_text())
    spec["input"].update(resize=CROP_RESIZE, resize_short_edge=20)
    model.write_text(json.dumps(spec))
    cropped = [(asset, observe_embeddings(asset, 0, model, every=1)[0]) for asset, _ in sources]
    model.parent.rename(tmp_path / "archived-model")
    with patch(
        "takebraid.adapters.models.onnx.importlib.import_module",
        side_effect=AssertionError("Replay must not import Pillow, NumPy or ONNX Runtime"),
    ):
        result = search_embeddings(cropped, tmp_path / "crop-search", min_cosine=1.0)
        record = json.loads(result.read_text())
        assert record["matching_pairs"] == 2 and record["unknown_pairs"] == 6
        assert search_embeddings(cropped, tmp_path / "crop-search", min_cosine=1.0) == result
        with pytest.raises(ValueError, match="Incompatible embedding spaces"):
            search_embeddings([sources[0], cropped[1]], tmp_path / "mixed", min_cosine=0.5)
