"""Generate an original numerical ONNX oracle; no pretrained model or semantic capability."""

import argparse
import hashlib
from pathlib import Path

from takebraid.adapters.artifacts import write_new_json


def generate(output: Path, *, mode="mean"):
    # Graph-construction dependency is development-only and imported on explicit invocation.
    import onnx
    from onnx import TensorProto, helper

    output.mkdir(parents=True, exist_ok=False)
    image = helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 16, 16])
    embedding = helper.make_tensor_value_info("embedding", TensorProto.FLOAT, [1, 3])
    if mode == "mean":
        nodes = [helper.make_node("ReduceMean", ["image"], ["embedding"], axes=[2, 3], keepdims=0)]
    elif mode == "nonfinite":
        tensor = helper.make_tensor("invalid", TensorProto.FLOAT, [1, 3], [float("nan")] * 3)
        nodes = [helper.make_node("Constant", [], ["embedding"], value=tensor)]
    else:
        raise ValueError("Unsupported oracle mode")
    graph = helper.make_graph(nodes, "synthetic-channel-mean-oracle", [image], [embedding])
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 13)],
        ir_version=8,
        producer_name="takebraid-synthetic-oracle",
    )
    onnx.checker.check_model(model)
    weights = output / "oracle.onnx"
    weights.write_bytes(model.SerializeToString())
    manifest = output / "model.json"
    write_new_json(
        manifest,
        {
            "schema_version": "0.1",
            "provider": "onnx-cpu",
            "model": {
                "file": weights.name,
                "sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "id": "synthetic-channel-mean-oracle",
                "revision": "oracle-1-" + mode,
                "license": "Apache-2.0",
                "source": "Original Takebraid graph recipe; not trained",
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
        },
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(generate(args.output))


if __name__ == "__main__":
    main()
