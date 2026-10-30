"""Single-file, hash-bound CPU ONNX image encoder with a declared preprocessing contract."""

import hashlib
import importlib
import math
import os
import platform
import re
import sys
import threading
from pathlib import Path

from takebraid.adapters.identity import file_digest
from takebraid.adapters.records import read_json
from takebraid.domain.embeddings import normalise_embedding

MAX_MODEL_BYTES = 512 * 1024 * 1024
_OWN_RUNTIME = None


def validate_model_spec(document: dict):
    """Validate declared metadata without opening weights or importing a runtime."""
    if (
        set(document) != {"schema_version", "provider", "model", "input", "output"}
        or document["schema_version"] != "0.1"
        or document["provider"] != "onnx-cpu"
    ):
        raise ValueError("Expected an explicit onnx-cpu model manifest")
    model, image, output = (document[k] for k in ("model", "input", "output"))
    if (
        set(model) != {"file", "sha256", "id", "revision", "license", "source", "usage_permitted"}
        or model["usage_permitted"] is not True
    ):
        raise ValueError("Declare model identity, revision, license, source and permitted use")
    for key in ("id", "revision", "license", "source"):
        if not isinstance(model[key], str) or not model[key].strip() or len(model[key]) > 2000:
            raise ValueError("Model provenance fields must be explicit bounded strings")
    filename = model["file"]
    if (
        not isinstance(filename, str)
        or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,120}\.onnx", filename)
        or not isinstance(model["sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", model["sha256"])
    ):
        raise ValueError("Model requires a sibling .onnx filename and SHA-256")
    if (
        set(image)
        != {"name", "width", "height", "layout", "dtype", "resize", "color", "mean", "std"}
        or image["layout"] != "NCHW"
        or image["dtype"] != "float32"
        or image["resize"] != "stretch-area"
        or image["color"] != "RGB"
        or any(type(image[k]) is not int or not 16 <= image[k] <= 512 for k in ("width", "height"))
    ):
        raise ValueError("Input must declare 16..512 RGB float32 NCHW stretch-area geometry")
    for key in ("mean", "std"):
        values = image[key]
        if (
            not isinstance(values, list)
            or len(values) != 3
            or any(
                type(v) not in (int, float)
                or not math.isfinite(v)
                or abs(v) > 10
                or (key == "std" and v < 1e-6)
                for v in values
            )
        ):
            raise ValueError("Declare three finite channel means/stds, with positive std >=1e-6")
    if (
        set(output) != {"name", "dimensions", "dtype"}
        or output["dtype"] != "float32"
        or type(output["dimensions"]) is not int
        or not 1 <= output["dimensions"] <= 4096
    ):
        raise ValueError("Output must declare 1..4096 float32 embedding dimensions")
    for tensor in (image, output):
        if not isinstance(tensor["name"], str) or not tensor["name"] or len(tensor["name"]) > 200:
            raise ValueError("Tensor names must be explicit bounded strings")


def load_model_manifest(path: Path):
    path = path.expanduser().resolve(strict=True)
    digest = file_digest(path)
    document = read_json(path, limit=64 * 1024)
    validate_model_spec(document)
    model = document["model"]
    weights = (path.parent / model["file"]).resolve(strict=True)
    if weights.parent != path.parent or weights.stat().st_size > MAX_MODEL_BYTES:
        raise ValueError("Single-file model must stay in its manifest directory and be <=512 MiB")
    if file_digest(weights) != model["sha256"] or file_digest(path) != digest:
        raise ValueError("Model or manifest checksum mismatch")
    return path, weights, document, digest


class LocalOnnxEncoder:
    def __init__(self, weights: Path, spec: dict):
        global _OWN_RUNTIME
        existing = sys.modules.get("onnxruntime")
        if existing is not None and existing is not _OWN_RUNTIME:
            raise ValueError(
                "ONNX Runtime already imported outside Takebraid; use a fresh process "
                "so telemetry can be disabled before initialization"
            )
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
        try:
            self.np = importlib.import_module("numpy")
            self.ort = importlib.import_module("onnxruntime")
            _OWN_RUNTIME = self.ort
        except ImportError as exc:
            raise ValueError(
                "Local ONNX provider unavailable; explicitly install takebraid[onnx]"
            ) from exc
        self.ort.disable_telemetry_events()
        self.spec = spec
        options = self.ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.execution_mode = self.ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = self.ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        with weights.open("rb") as source:
            payload = source.read(MAX_MODEL_BYTES + 1)
        if (
            len(payload) > MAX_MODEL_BYTES
            or hashlib.sha256(payload).hexdigest() != spec["model"]["sha256"]
        ):
            raise ValueError("Model changed before session creation")
        try:
            self.session = self.ort.InferenceSession(
                payload, sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise ValueError(f"Cannot load single-file local ONNX model: {exc}") from exc
        image, output = spec["input"], spec["output"]
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (
            len(inputs) != 1
            or len(outputs) != 1
            or inputs[0].name != image["name"]
            or inputs[0].type != "tensor(float)"
            or inputs[0].shape != [1, 3, image["height"], image["width"]]
            or outputs[0].name != output["name"]
            or outputs[0].type != "tensor(float)"
            or outputs[0].shape != [1, output["dimensions"]]
            or self.session.get_providers() != ["CPUExecutionProvider"]
        ):
            raise ValueError("ONNX tensor names/types/static shapes differ from the manifest")
        self.runtime = {
            "onnxruntime": self.ort.__version__,
            "numpy": self.np.__version__,
            "build": self.ort.get_build_info(),
            "provider": "CPUExecutionProvider",
            "telemetry": "disabled",
            "initialization_guard": "ORT_DISABLE_TELEMETRY=1-before-owned-import",
            "threads": 1,
            "execution": "sequential",
            "graph_optimization": "disabled",
            "platform": platform.platform(),
            "machine": platform.machine(),
        }

    def encode(self, pixels: bytes, timeout: float):
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 300
        ):
            raise ValueError("Inference deadline must be >0 and <=300 seconds")
        np, image = self.np, self.spec["input"]
        expected = image["width"] * image["height"] * 3
        if len(pixels) != expected:
            raise ValueError("RGB frame length differs from model input geometry")
        tensor = np.frombuffer(pixels, dtype=np.uint8).reshape(image["height"], image["width"], 3)
        tensor = tensor.astype(np.float32) / np.float32(255)
        tensor = (tensor - np.asarray(image["mean"], dtype=np.float32)) / np.asarray(
            image["std"], dtype=np.float32
        )
        tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None, ...])
        options = self.ort.RunOptions()
        timer = threading.Timer(timeout, lambda: setattr(options, "terminate", True))
        timer.daemon = True
        timer.start()
        try:
            result = self.session.run(
                [self.spec["output"]["name"]], {image["name"]: tensor}, options
            )[0]
        except Exception as exc:
            raise ValueError(
                f"Local ONNX inference failed or exceeded its cooperative deadline: {exc}"
            ) from exc
        finally:
            timer.cancel()
        if (
            not isinstance(result, np.ndarray)
            or result.dtype != np.float32
            or list(result.shape) != [1, self.spec["output"]["dimensions"]]
        ):
            raise ValueError("Model output is not its declared float32 [1,D] tensor")
        return normalise_embedding(result[0].tolist(), self.spec["output"]["dimensions"])
