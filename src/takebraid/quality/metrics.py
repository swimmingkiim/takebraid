"""Exact 8-bit grayscale statistics on a fixed analysis grid."""

from fractions import Fraction

from takebraid.domain.quality import QualityMetrics, QualitySettings
from takebraid.domain.time import _require_int


def measure_gray(data: bytes, width: int, height: int, settings: QualitySettings) -> QualityMetrics:
    for value in (width, height):
        _require_int(value, "analysis dimension")
        if value < 3:
            raise ValueError("Analysis dimensions must be at least 3")
    if not isinstance(data, bytes):
        raise TypeError("Grayscale input must be bytes")
    if len(data) != width * height:
        raise ValueError("Grayscale buffer does not match its dimensions")
    x, y, w, h = settings.region(width, height)
    pixels = [data[row * width + col] for row in range(y, y + h) for col in range(x, x + w)]
    count = len(pixels)
    mean = Fraction(sum(pixels), count)
    variance = Fraction(sum(v * v for v in pixels), count) - mean * mean
    total = squared = 0
    for row in range(y + 1, y + h - 1):
        for col in range(x + 1, x + w - 1):
            index = row * width + col
            lap = (
                data[index - 1]
                + data[index + 1]
                + data[index - width]
                + data[index + width]
                - 4 * data[index]
            )
            total += lap
            squared += lap * lap
    interior = (w - 2) * (h - 2)
    lap_variance = Fraction(squared, interior) - Fraction(total, interior) ** 2
    return QualityMetrics(
        mean / 255,
        variance / (255 * 255),
        Fraction(sum(v <= 16 for v in pixels), count),
        Fraction(sum(v >= 235 for v in pixels), count),
        lap_variance / (255 * 255),
    )
