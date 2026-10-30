import copy
import hashlib
import json
from pathlib import Path

import pytest

from takebraid.adapters.models.onnx import validate_model_spec
from takebraid.adapters.models.preprocessing import CROP_RESIZE, PillowCrop, crop_geometry
from tools.check_embedding_preprocessing import IMAGE_SPEC, pattern


def test_resize_preserves_aspect_ratio_floor_and_round_to_even_crop_offsets():
    assert crop_geometry((513, 257), IMAGE_SPEC) == ((511, 256), (144, 16, 368, 240))
    assert crop_geometry((257, 513), IMAGE_SPEC) == ((256, 511), (16, 144, 240, 368))
    assert crop_geometry((300, 300), IMAGE_SPEC) == ((256, 256), (16, 16, 240, 240))
    with pytest.raises(ValueError, match="megapixel"):
        crop_geometry((16384, 3), IMAGE_SPEC)
    with pytest.raises(ValueError, match="integers"):
        crop_geometry((True, 30), IMAGE_SPEC)


@pytest.mark.parametrize("edge", [True, 15, 1025, 256.0, None])
def test_manifest_rejects_implicit_padding_or_unbounded_resize(edge):
    from tests.test_embeddings import manifest_document

    document = copy.deepcopy(manifest_document())
    document["input"].update(resize=CROP_RESIZE, resize_short_edge=edge)
    with pytest.raises(ValueError, match="resize_short_edge"):
        validate_model_spec(document)


def test_pillow_is_an_explicit_optional_dependency(monkeypatch):
    def missing(name):
        raise ImportError("No optional image dependency")

    monkeypatch.setattr("takebraid.adapters.models.preprocessing.importlib.import_module", missing)
    with pytest.raises(ValueError, match="image-preprocessing"):
        PillowCrop()


@pytest.mark.onnx
def test_pixels_match_preserved_independent_torchvision_golden_report():
    pytest.importorskip("PIL")
    report = json.loads(
        (Path(__file__).parent / "fixtures" / "embedding-preprocessing-reference.json").read_text()
    )
    preprocessor = PillowCrop()
    assert preprocessor.version == report["reference"]["pillow"]
    for case in report["cases"]:
        shape = case["source_geometry"]
        pixels = pattern(*shape)
        assert hashlib.sha256(pixels).hexdigest() == case["source_sha256"]
        actual = preprocessor.apply(pixels, shape, report["preprocessing"])
        assert hashlib.sha256(actual).hexdigest() == case["crop_sha256"]
    with pytest.raises(ValueError, match="length"):
        preprocessor.apply(b"", (16, 16), IMAGE_SPEC)
