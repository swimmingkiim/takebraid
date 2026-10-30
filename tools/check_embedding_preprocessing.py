"""Compare optional crop preprocessing with torchvision's independent PIL reference.

Explicit checkout-only validation; no weights, media, network or application defaults.
Use an isolated environment with torch==2.6.0, torchvision==0.21.0, Pillow==13.0.0,
and numpy==2.3.5. The original RGB patterns are project-authored Apache-2.0 fixtures.
"""

import argparse
import hashlib
from pathlib import Path

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.models.preprocessing import CROP_RESIZE, PillowCrop

SOURCE_SHAPES = [(300, 300), (513, 257), (257, 513), (640, 360), (360, 640), (225, 226), (37, 19)]
IMAGE_SPEC = {
    "width": 224,
    "height": 224,
    "resize": CROP_RESIZE,
    "resize_short_edge": 256,
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
}


def pattern(width, height):
    return bytes(
        value
        for y in range(height)
        for x in range(width)
        for value in ((x * 17 + y * 3) % 256, (x * 5 + y * 29) % 256, (x ^ y) % 256)
    )


def check_reference(output):
    # Heavy reference libraries are not imported by the CLI, tests or core package.
    import numpy as np
    import PIL
    import torch
    import torchvision
    from PIL import Image
    from torchvision import transforms

    reference = transforms.Compose(
        [
            transforms.Resize(
                256, interpolation=transforms.InterpolationMode.BICUBIC, antialias=True
            ),
            transforms.CenterCrop((224, 224)),
        ]
    )
    normalize = transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize(IMAGE_SPEC["mean"], IMAGE_SPEC["std"])]
    )
    preprocessor, cases = PillowCrop(), []
    for shape in SOURCE_SHAPES:
        pixels = pattern(*shape)
        actual = preprocessor.apply(pixels, shape, IMAGE_SPEC)
        with Image.frombytes("RGB", shape, pixels) as image:
            expected = reference(image)
            if actual != expected.tobytes():
                raise ValueError(f"Crop pixels differ from torchvision for {shape}")
            tensor = np.frombuffer(actual, dtype=np.uint8).reshape(224, 224, 3)
            tensor = tensor.astype(np.float32) / np.float32(255)
            tensor = (tensor - np.asarray(IMAGE_SPEC["mean"], dtype=np.float32)) / np.asarray(
                IMAGE_SPEC["std"], dtype=np.float32
            )
            error = float(np.abs(tensor.transpose(2, 0, 1) - normalize(expected).numpy()).max())
            expected.close()
        if not np.isfinite(error) or error > 1e-6:
            raise ValueError(f"Normalized tensor differs from torchvision for {shape}: {error}")
        cases.append(
            {
                "source_geometry": list(shape),
                "source_sha256": hashlib.sha256(pixels).hexdigest(),
                "crop_sha256": hashlib.sha256(actual).hexdigest(),
                "pixels_byte_identical": True,
                "normalized_max_abs_error": error,
            }
        )
    report = {
        "schema_version": "0.1",
        "scope": "constructed_RGB_preprocessing_reference_only",
        "reference": {
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "pillow": PIL.__version__,
            "numpy": np.__version__,
            "dinov2_transform_revision": "7764ea0f912e53c92e82eb78a2a1631e92725fc8",
        },
        "preprocessing": IMAGE_SPEC,
        "normalized_atol": 1e-6,
        "cases": cases,
        "learned_checkpoint_validated": False,
        "semantic_accuracy_validated": False,
    }
    write_new_json(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New report JSON; never overwritten"
    )
    args = parser.parse_args()
    check_reference(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
