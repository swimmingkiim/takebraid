"""Explicit calibration-scoped temporal rules and exact source evidence cells."""

import re
from dataclasses import dataclass
from fractions import Fraction

from takebraid.domain.time import _require_int

METRICS = {
    "laplacian_variance": ("quality", "low", Fraction(16)),
    "dark_fraction": ("quality", "high", Fraction(1)),
    "bright_fraction": ("quality", "high", Fraction(1)),
    "path_residual_squared": ("motion", "high", None),
}


@dataclass(frozen=True)
class TemporalPolicy:
    name: str
    calibration: str
    metric: str
    enter: Fraction
    exit: Fraction
    minimum_seconds: Fraction
    pad_before_seconds: Fraction
    pad_after_seconds: Fraction

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", self.name):
            raise ValueError("Policy name must be a short lowercase identifier")
        if (
            not isinstance(self.calibration, str)
            or not self.calibration.strip()
            or len(self.calibration) > 1000
        ):
            raise ValueError("An explicit calibration context is required")
        if self.metric not in METRICS:
            raise ValueError("Unsupported temporal metric")
        kind, direction, maximum = METRICS[self.metric]
        values = (
            self.enter,
            self.exit,
            self.minimum_seconds,
            self.pad_before_seconds,
            self.pad_after_seconds,
        )
        if any(not isinstance(v, Fraction) for v in values):
            raise TypeError("Policy numbers must be exact rationals")
        if any(v < 0 or abs(v.numerator) > 10**12 or v.denominator > 10**9 for v in values):
            raise ValueError("Policy rational out of bounds")
        if maximum is not None and max(self.enter, self.exit) > maximum:
            raise ValueError("Threshold exceeds the metric's mathematical range")
        if (direction == "low" and self.enter >= self.exit) or (
            direction == "high" and self.enter <= self.exit
        ):
            raise ValueError("Enter/exit thresholds must define a nonempty hysteresis band")
        if (
            not 0 < self.minimum_seconds <= 3600
            or max(self.pad_before_seconds, self.pad_after_seconds) > 60
        ):
            raise ValueError("Minimum duration must be (0,3600] seconds; padding 0..60 seconds")

    @property
    def source_kind(self):
        return METRICS[self.metric][0]

    def enters(self, value):
        return value <= self.enter if METRICS[self.metric][1] == "low" else value >= self.enter

    def leaves(self, value):
        return value >= self.exit if METRICS[self.metric][1] == "low" else value <= self.exit


@dataclass(frozen=True)
class EvidenceCell:
    in_pts: int
    out_pts: int
    value: Fraction | None
    evidence_index: int | None
    reason: str | None = None

    def __post_init__(self):
        _require_int(self.in_pts, "cell in")
        _require_int(self.out_pts, "cell out")
        if self.in_pts >= self.out_pts:
            raise ValueError("Evidence cell must be nonempty")
        if self.value is None:
            if (
                self.evidence_index is not None
                or not isinstance(self.reason, str)
                or not self.reason
            ):
                raise ValueError("Unknown cell needs a reason and no evidence index")
        elif not isinstance(self.value, Fraction) or self.value < 0 or self.reason is not None:
            raise ValueError("Observed cell needs a nonnegative rational and no unknown reason")
        else:
            _require_int(self.evidence_index, "evidence index")
            if self.evidence_index < 0:
                raise ValueError("Evidence index must be nonnegative")
