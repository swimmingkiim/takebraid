"""Explicit optional RGB preprocessing; never resize a previously stretched frame."""

import importlib

CROP_RESIZE = "pillow-bicubic-short-edge-center-crop/1"
MAX_IMAGE_PIXELS = 16 * 1024 * 1024


def crop_geometry(source_geometry, image):
    """Match torchvision's PIL integer short-edge resize and round-to-even center crop."""
    if (
        not isinstance(source_geometry, (tuple, list))
        or len(source_geometry) != 2
        or any(type(v) is not int or not 3 <= v <= 16384 for v in source_geometry)
    ):
        raise ValueError("RGB source geometry must contain two integers in 3..16384")
    width, height = source_geometry
    edge = image["resize_short_edge"]
    resized = (edge, edge * height // width) if width <= height else (edge * width // height, edge)
    if width * height > MAX_IMAGE_PIXELS or resized[0] * resized[1] > MAX_IMAGE_PIXELS:
        raise ValueError("RGB preprocessing exceeds 16 megapixel source/resized frame budget")
    left = round((resized[0] - image["width"]) / 2)
    top = round((resized[1] - image["height"]) / 2)
    return resized, (left, top, left + image["width"], top + image["height"])


class PillowCrop:
    def __init__(self):
        try:
            self.image = importlib.import_module("PIL.Image")
            self.version = importlib.import_module("PIL").__version__
        except ImportError as exc:
            raise ValueError(
                "Bicubic crop preprocessing unavailable; explicitly install "
                "takebraid[image-preprocessing]"
            ) from exc

    def apply(self, pixels: bytes, source_geometry, image):
        resized, box = crop_geometry(source_geometry, image)
        width, height = source_geometry
        if len(pixels) != width * height * 3:
            raise ValueError("RGB frame length differs from original source geometry")
        with self.image.frombytes("RGB", (width, height), pixels) as source:
            with source.resize(resized, self.image.Resampling.BICUBIC, reducing_gap=None) as scaled:
                with scaled.crop(box) as cropped:
                    return cropped.tobytes()
