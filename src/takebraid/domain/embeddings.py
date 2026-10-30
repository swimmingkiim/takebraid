"""Numerical embedding invariants; media clocks are kept separately as exact source values."""

import math


def normalise_embedding(values: list[float], dimensions: int):
    if (
        type(dimensions) is not int
        or not 1 <= dimensions <= 4096
        or not isinstance(values, list)
        or len(values) != dimensions
        or any(type(v) is not float for v in values)
    ):
        raise ValueError("Embedding must have its declared float dimensions")
    if not all(math.isfinite(v) for v in values):
        return None, "nonfinite_model_output"
    norm = math.hypot(*values)
    if norm == 0:
        return None, "zero_model_output"
    return [v / norm for v in values], None


def validate_unit_vector(values, dimensions):
    if (
        not isinstance(values, list)
        or len(values) != dimensions
        or any(type(v) is not float or not math.isfinite(v) for v in values)
        or not math.isclose(math.hypot(*values), 1.0, rel_tol=0, abs_tol=1e-6)
    ):
        raise ValueError("Saved embedding must be a finite unit vector of the declared dimensions")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions differ")
    validate_unit_vector(left, len(left))
    validate_unit_vector(right, len(right))
    if left == right:
        return 1.0
    score = math.fsum(a * b for a, b in zip(left, right, strict=True)) / (
        math.hypot(*left) * math.hypot(*right)
    )
    return max(-1.0, min(1.0, score))


def search_series(series: list[dict], dimensions: int, min_cosine: float, limit: int):
    if (
        type(dimensions) is not int
        or not 1 <= dimensions <= 4096
        or type(min_cosine) is not float
        or not math.isfinite(min_cosine)
        or not -1 <= min_cosine <= 1
        or type(limit) is not int
        or not 1 <= limit <= 1000
    ):
        raise ValueError("Use finite cosine -1..1, dimensions 1..4096 and limit 1..1000")
    if not 2 <= len(series) <= 10 or len({s["asset_id"] for s in series}) != len(series):
        raise ValueError("Search requires 2..10 distinct source assets")
    series = sorted(series, key=lambda s: s["asset_id"])
    sample_count = sum(len(s["rows"]) for s in series)
    if sample_count > 2000 or sample_count * dimensions > 2000000:
        raise ValueError("Search exceeds 2000 samples or 2000000 vector coordinates")
    possible = sum(
        len(a["rows"]) * len(b["rows"]) for i, a in enumerate(series) for b in series[i + 1 :]
    )
    if possible > 50000 or possible * dimensions > 8000000:
        raise ValueError("Search exceeds 50000 pairs or 8000000 pair coordinates; increase --every")
    valid = {}
    for s in series:
        valid[s["asset_id"]] = []
        for row in s["rows"]:
            if row["values"] is not None:
                validate_unit_vector(row["values"], dimensions)
                valid[s["asset_id"]].append(row)
    matches, evaluated = [], 0
    for i, a in enumerate(series):
        for b in series[i + 1 :]:
            for left in valid[a["asset_id"]]:
                for right in valid[b["asset_id"]]:
                    evaluated += 1
                    score = cosine_similarity(left["values"], right["values"])
                    if score >= min_cosine:
                        matches.append(
                            {
                                "cosine": score,
                                "left": {"asset_id": a["asset_id"], **left["point"]},
                                "right": {"asset_id": b["asset_id"], **right["point"]},
                            }
                        )
    matches.sort(
        key=lambda m: (
            -m["cosine"],
            m["left"]["asset_id"],
            m["left"]["frame_index"],
            m["right"]["asset_id"],
            m["right"]["frame_index"],
        )
    )
    return {
        "sampled_frames": sample_count,
        "possible_pairs": possible,
        "evaluated_pairs": evaluated,
        "unknown_pairs": possible - evaluated,
        "unknown_samples": {
            s["asset_id"]: len(s["rows"]) - len(valid[s["asset_id"]]) for s in series
        },
        "matching_pairs": len(matches),
        "truncated_pairs": max(0, len(matches) - limit),
        "matches": matches[:limit],
    }
