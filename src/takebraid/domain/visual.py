"""Transparent spatial descriptors and bounded visual matches; no semantic or editing verdicts."""

from dataclasses import dataclass
from fractions import Fraction

GRID = 8
DIMENSIONS = GRID * GRID
MAX_PAIRS = 50000


@dataclass(frozen=True)
class GridDescriptor:
    values: tuple[Fraction, ...]

    def __post_init__(self):
        if (
            not isinstance(self.values, tuple)
            or len(self.values) != DIMENSIONS
            or any(not isinstance(v, Fraction) or not 0 <= v <= 1 for v in self.values)
        ):
            raise ValueError("Expected 64 exact normalized grayscale cell means")

    @property
    def variance(self) -> Fraction:
        mean = sum(self.values) / DIMENSIONS
        return sum((v - mean) ** 2 for v in self.values) / DIMENSIONS


def describe_gray(pixels: bytes, width: int, height: int) -> GridDescriptor:
    if (
        type(width) is not int
        or type(height) is not int
        or min(width, height) < GRID
        or len(pixels) != width * height
    ):
        raise ValueError("Descriptor needs a complete grayscale grid at least 8x8")
    cells = []
    for gy in range(GRID):
        top, bottom = gy * height // GRID, (gy + 1) * height // GRID
        for gx in range(GRID):
            left, right = gx * width // GRID, (gx + 1) * width // GRID
            total = sum(
                sum(pixels[y * width + left : y * width + right]) for y in range(top, bottom)
            )
            cells.append(Fraction(total, (right - left) * (bottom - top) * 255))
    return GridDescriptor(tuple(cells))


def squared_distance(left: GridDescriptor, right: GridDescriptor) -> Fraction:
    return sum((a - b) ** 2 for a, b in zip(left.values, right.values, strict=True)) / DIMENSIONS


def match_series(series: list[dict], max_distance: Fraction, min_variance: Fraction, limit: int):
    if (
        not isinstance(max_distance, Fraction)
        or not 0 <= max_distance <= 1
        or not isinstance(min_variance, Fraction)
        or not 0 < min_variance <= Fraction(1, 4)
        or type(limit) is not int
        or not 1 <= limit <= 1000
    ):
        raise ValueError("Use distance 0..1, positive variance <=1/4 and limit 1..1000")
    if not 2 <= len(series) <= 10 or len({s["asset_id"] for s in series}) != len(series):
        raise ValueError("Compare 2..10 distinct source assets")
    series = sorted(series, key=lambda s: s["asset_id"])
    pairs = sum(
        len(a["rows"]) * len(b["rows"]) for i, a in enumerate(series) for b in series[i + 1 :]
    )
    if pairs > MAX_PAIRS:
        raise ValueError("Comparison exceeds 50000 sampled pairs; increase observation --every")
    # Filter low spatial contrast before scoring; it is insufficient match evidence, not a defect.
    eligible = {
        s["asset_id"]: [r for r in s["rows"] if r["descriptor"].variance >= min_variance]
        for s in series
    }
    matches, evaluated, incompatible = [], 0, 0
    for i, a in enumerate(series):
        for b in series[i + 1 :]:
            if a["aspect"] != b["aspect"]:
                incompatible += len(a["rows"]) * len(b["rows"])
                continue
            for left in eligible[a["asset_id"]]:
                for right in eligible[b["asset_id"]]:
                    evaluated += 1
                    distance = squared_distance(left["descriptor"], right["descriptor"])
                    if distance <= max_distance:
                        matches.append(
                            {
                                "distance": distance,
                                "left": {"asset_id": a["asset_id"], **left["point"]},
                                "right": {"asset_id": b["asset_id"], **right["point"]},
                            }
                        )
    matches.sort(
        key=lambda m: (
            m["distance"],
            m["left"]["asset_id"],
            m["left"]["frame_index"],
            m["right"]["asset_id"],
            m["right"]["frame_index"],
        )
    )
    return {
        "sampled_pairs": pairs,
        "evaluated_pairs": evaluated,
        "incompatible_aspect_pairs": incompatible,
        "low_texture_samples": {
            s["asset_id"]: len(s["rows"]) - len(eligible[s["asset_id"]]) for s in series
        },
        "matching_pairs": len(matches),
        "truncated_pairs": max(0, len(matches) - limit),
        "matches": matches[:limit],
    }
