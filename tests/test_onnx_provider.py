import pytest

from takebraid.adapters.models.onnx import LocalOnnxEncoder, load_model_manifest
from tools.embedding_fixture import generate

pytestmark = pytest.mark.onnx


@pytest.fixture
def model(tmp_path):
    pytest.importorskip("onnx")
    from importlib.util import find_spec

    if find_spec("onnxruntime") is None:
        pytest.skip("optional ONNX runtime unavailable")
    return generate(tmp_path / "model")


def test_real_onnx_cpu_channel_order_normalization_and_shape(model):
    import math

    _, weights, spec, _ = load_model_manifest(model)
    encoder = LocalOnnxEncoder(weights, spec)
    values, reason = encoder.encode(bytes([64, 128, 192]) * 16 * 16, 5)
    assert reason is None
    norm = math.hypot(64, 128, 192)
    assert values == pytest.approx([64 / norm, 128 / norm, 192 / norm], abs=1e-6)
    assert encoder.encode(bytes(16 * 16 * 3), 5) == (None, "zero_model_output")
    assert encoder.runtime["provider"] == "CPUExecutionProvider"
    assert encoder.runtime["telemetry"] == "disabled"
    spec["output"]["dimensions"] = 4
    with pytest.raises(ValueError, match="shapes"):
        LocalOnnxEncoder(weights, spec)


def test_real_nonfinite_model_output_becomes_unknown(model, tmp_path):
    path = generate(tmp_path / "nonfinite", mode="nonfinite")
    _, weights, spec, _ = load_model_manifest(path)
    assert LocalOnnxEncoder(weights, spec).encode(bytes(16 * 16 * 3), 5) == (
        None,
        "nonfinite_model_output",
    )


def test_weight_mutation_is_rejected_before_session_creation(model):
    _, weights, spec, _ = load_model_manifest(model)
    weights.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        LocalOnnxEncoder(weights, spec)


def test_cooperative_deadline_error_is_reported_without_hanging(model, monkeypatch):
    _, weights, spec, _ = load_model_manifest(model)
    encoder = LocalOnnxEncoder(weights, spec)

    class ImmediateTimer:
        def __init__(self, duration, callback):
            self.callback = callback

        def start(self):
            self.callback()

        def cancel(self):
            pass

    monkeypatch.setattr("takebraid.adapters.models.onnx.threading.Timer", ImmediateTimer)
    with pytest.raises(ValueError, match="deadline"):
        encoder.encode(bytes([128]) * 16 * 16 * 3, 5)


def test_external_initializer_file_is_not_implicitly_loaded(model, tmp_path):
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", ["image"], ["means"], axes=[2, 3], keepdims=0),
            helper.make_node("Add", ["means", "bias"], ["embedding"]),
        ],
        "external-oracle",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 16, 16])],
        [helper.make_tensor_value_info("embedding", TensorProto.FLOAT, [1, 3])],
        [numpy_helper.from_array(np.zeros((1, 3), dtype=np.float32), name="bias")],
    )
    external = tmp_path / "external.onnx"
    graph_model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=8
    )
    onnx.save_model(
        graph_model,
        external,
        save_as_external_data=True,
        all_tensors_to_one_file=True,
        location="external.bin",
        size_threshold=0,
    )
    _, _, spec, _ = load_model_manifest(model)
    import hashlib

    spec["model"]["sha256"] = hashlib.sha256(external.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="single-file"):
        LocalOnnxEncoder(external, spec)
