import copy
import hashlib
import json
import math
import subprocess
import sys

import pytest

from takebraid.adapters.models.onnx import LocalOnnxEncoder, load_model_manifest
from takebraid.domain.embeddings import normalise_embedding, validate_unit_vector


def manifest_document():
    return {
        "schema_version": "0.1",
        "provider": "onnx-cpu",
        "model": {
            "file": "encoder.onnx",
            "sha256": hashlib.sha256(b"model").hexdigest(),
            "id": "test",
            "revision": "v1",
            "license": "Apache-2.0",
            "source": "Test fixture",
            "usage_permitted": True,
        },
        "input": {
            "name": "image",
            "width": 16,
            "height": 16,
            "layout": "NCHW",
            "dtype": "float32",
            "resize": "stretch-area",
            "color": "RGB",
            "mean": [0, 0, 0],
            "std": [1, 1, 1],
        },
        "output": {"name": "embedding", "dimensions": 3, "dtype": "float32"},
    }


def test_normalization_is_numerically_bounded_and_unknown_is_preserved():
    values, reason = normalise_embedding([3.0, 4.0], 2)
    assert values == [0.6, 0.8] and reason is None
    validate_unit_vector(values, 2)
    assert normalise_embedding([0.0, 0.0], 2) == (None, "zero_model_output")
    assert normalise_embedding([float("nan")], 1) == (None, "nonfinite_model_output")
    assert normalise_embedding([float("inf")], 1) == (None, "nonfinite_model_output")
    values, reason = normalise_embedding([3e38, 4e38], 2)
    assert math.hypot(*values) == 1 and reason is None


@pytest.mark.parametrize("values", [[0.0, 0.0], [1.0], [float("nan"), 1.0], [1, 0], [True, 0.0]])
def test_saved_embedding_dimension_unit_norm_and_finite_values_are_checked(values):
    with pytest.raises(ValueError):
        validate_unit_vector(values, 2)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("model", "file", "../encoder.onnx"),
        ("model", "file", "https://example.com/encoder.onnx"),
        ("model", "sha256", "0" * 64),
        ("model", "revision", ""),
        ("model", "usage_permitted", False),
        ("input", "width", True),
        ("input", "height", 513),
        ("input", "layout", "NHWC"),
        ("input", "resize", "automatic"),
        ("input", "mean", [0, 0]),
        ("input", "std", [1, 0, 1]),
        ("output", "dimensions", 4097),
        ("output", "dtype", "float64"),
    ],
)
def test_manifest_rejects_unpinned_paths_provenance_or_unsupported_preprocessing(
    tmp_path, section, key, value
):
    document = copy.deepcopy(manifest_document())
    document[section][key] = value
    (tmp_path / "encoder.onnx").write_bytes(b"model")
    path = tmp_path / "model.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_model_manifest(path)


def test_model_manifest_is_usable_without_importing_optional_runtime(tmp_path):
    (tmp_path / "encoder.onnx").write_bytes(b"model")
    path = tmp_path / "model.json"
    path.write_text(json.dumps(manifest_document()))
    _, weights, spec, _ = load_model_manifest(path)
    assert weights.read_bytes() == b"model" and spec["input"]["width"] == 16


def test_missing_optional_runtime_is_an_actionable_error(tmp_path, monkeypatch):
    def missing(name):
        raise ImportError("Explicit missing dependency simulation")

    monkeypatch.setattr("takebraid.adapters.models.onnx.importlib.import_module", missing)
    with pytest.raises(ValueError, match=r"takebraid\[onnx\]"):
        LocalOnnxEncoder(tmp_path / "not-read.onnx", manifest_document())


def test_basic_cli_does_not_import_model_runtimes_even_when_installed():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from takebraid.cli import main; "
            "assert 'numpy' not in sys.modules; assert 'onnxruntime' not in sys.modules; "
            "main(['--version'])",
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )


def test_preimported_runtime_is_rejected_before_loading_models(tmp_path, monkeypatch):
    from takebraid.adapters.models import onnx

    monkeypatch.setitem(sys.modules, "onnxruntime", object())
    monkeypatch.setattr(onnx, "_OWN_RUNTIME", None)
    with pytest.raises(ValueError, match="fresh process"):
        LocalOnnxEncoder(tmp_path / "never-read.onnx", manifest_document())
