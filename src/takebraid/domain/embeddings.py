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
