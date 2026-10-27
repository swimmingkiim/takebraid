"""Bounded motion settings; observations are not camera/shake verdicts."""

from dataclasses import dataclass

from takebraid.domain.quality import QualitySettings
from takebraid.domain.time import _require_int


@dataclass(frozen=True)
class MotionSettings:
    size: int = 96
    every: int = 1
    radius: int = 4
    background: tuple[int, int, int, int] | None = None

    def __post_init__(self):
        QualitySettings(self.size, self.every, self.background)
        _require_int(self.radius, "search radius")
        if not 32 <= self.size <= 192 or not 2 <= self.radius <= 6:
            raise ValueError("Motion size must be 32..192 and search radius 2..6")
        if self.background is not None and min(self.background[2:]) < 2 * self.radius + 10:
            raise ValueError("Background region is too small for the patch/search grid")

    def grid(self) -> QualitySettings:
        return QualitySettings(self.size, self.every, self.background)
