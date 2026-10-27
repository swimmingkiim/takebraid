"""Measurement settings and invariants; no editorial verdicts or media dependencies."""

from dataclasses import dataclass
from fractions import Fraction

from takebraid.domain.time import _require_int


@dataclass(frozen=True)
class QualitySettings:
    size: int = 160
    every: int = 1
    roi: tuple[int, int, int, int] | None = None

    def __post_init__(self):
        _require_int(self.size, "size")
        _require_int(self.every, "every")
        if not 16 <= self.size <= 512 or not 1 <= self.every <= 250000:
            raise ValueError("Analysis size must be 16..512 and sampling stride 1..250000")
        if self.roi is not None:
            if not isinstance(self.roi, tuple) or len(self.roi) != 4:
                raise ValueError("ROI must be X:Y:WIDTH:HEIGHT on the analysis pixel grid")
            for value in self.roi:
                _require_int(value, "ROI coordinate")
            x, y, width, height = self.roi
            if x < 0 or y < 0 or width < 3 or height < 3:
                raise ValueError("ROI origin must be nonnegative and dimensions at least 3")

    def geometry(self, width: int, height: int) -> tuple[int, int]:
        for value in (width, height):
            _require_int(value, "source dimension")
            if value < 3:
                raise ValueError("Source dimensions must be at least 3")
        divisor = max(width, height, self.size)
        result = (width * self.size // divisor, height * self.size // divisor)
        if min(result) < 3:
            raise ValueError("Analysis geometry is too small")
        self.region(*result)
        return result

    def region(self, width: int, height: int) -> tuple[int, int, int, int]:
        x, y, w, h = self.roi or (0, 0, width, height)
        if x + w > width or y + h > height:
            raise ValueError("ROI exceeds the analysis pixel grid")
        return x, y, w, h


@dataclass(frozen=True)
class QualityMetrics:
    mean_luma: Fraction
    luma_variance: Fraction
    dark_fraction: Fraction
    bright_fraction: Fraction
    laplacian_variance: Fraction

    def __post_init__(self):
        for value in (
            self.mean_luma,
            self.luma_variance,
            self.dark_fraction,
            self.bright_fraction,
            self.laplacian_variance,
        ):
            if not isinstance(value, Fraction):
                raise TypeError("Quality measurements must be exact rational values")
        if (
            not 0 <= self.mean_luma <= 1
            or not 0 <= self.luma_variance <= Fraction(1, 4)
            or not 0 <= self.dark_fraction <= 1
            or not 0 <= self.bright_fraction <= 1
            or self.dark_fraction + self.bright_fraction > 1
            or not 0 <= self.laplacian_variance <= 16
        ):
            raise ValueError("Quality measurement outside its mathematical bounds")
