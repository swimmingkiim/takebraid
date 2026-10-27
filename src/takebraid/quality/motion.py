"""Deterministic integer patch correspondences and conservative translation consensus."""

from collections import Counter
from fractions import Fraction

from takebraid.domain.motion import MotionSettings

PATCH = 5
MIN_TEXTURE_VARIANCE = 64
MAX_SAD = 500
MIN_MARGIN = 125
MIN_TRACKS = 12
MIN_INLIERS = 8


def patch(data: bytes, width: int, x: int, y: int) -> bytes:
    return b"".join(data[row * width + x - 2 : row * width + x + 3] for row in range(y - 2, y + 3))


def textured(values: bytes) -> bool:
    return (
        len(values) == 25
        and 25 * sum(v * v for v in values) - sum(values) ** 2 >= 625 * MIN_TEXTURE_VARIANCE
    )


def match(values, target, width, x, y, region, radius):
    rx, ry, rw, rh = region
    costs = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            cx, cy = x + dx, y + dy
            if not (rx + 2 <= cx < rx + rw - 2 and ry + 2 <= cy < ry + rh - 2):
                continue
            other = patch(target, width, cx, cy)
            cost = sum(abs(a - b) for a, b in zip(values, other, strict=True))
            costs.append((cost, dx, dy))
    costs.sort()
    if len(costs) < 2:
        return None, "ambiguous"
    best, second = costs[:2]
    if best[0] > MAX_SAD:
        return None, "photometric_mismatch"
    if second[0] - best[0] < MIN_MARGIN:
        return None, "ambiguous"
    if abs(best[1]) == radius or abs(best[2]) == radius:
        return None, "search_boundary"
    return best, None


def summarize_tracks(tracks: list[dict], region: tuple[int, int, int, int]) -> dict:
    """Recompute consensus from saved evidence, including rejected independent motions."""
    if len(tracks) < MIN_TRACKS:
        return {
            "status": "unknown",
            "reason": "insufficient_tracks",
            "translation": None,
            "inlier_indices": [],
            "residual_squared": None,
        }
    # Exact-vector mode; ties never silently choose one of two competing motions.
    counts = Counter((t["dx"], t["dy"]) for t in tracks)
    candidates = counts.most_common()
    if len(candidates) > 1 and candidates[0][1] == candidates[1][1]:
        return {
            "status": "unknown",
            "reason": "ambiguous_consensus",
            "translation": None,
            "inlier_indices": [],
            "residual_squared": None,
        }
    dx, dy = candidates[0][0]
    inliers = [i for i, t in enumerate(tracks) if (t["dx"] - dx) ** 2 + (t["dy"] - dy) ** 2 <= 1]
    x, y, w, h = region
    quadrants = {
        2 * int(2 * (tracks[i]["y"] - y) >= h) + int(2 * (tracks[i]["x"] - x) >= w) for i in inliers
    }
    if len(inliers) < MIN_INLIERS or 5 * len(inliers) < 3 * len(tracks) or len(quadrants) != 4:
        return {
            "status": "unknown",
            "reason": "insufficient_spatial_consensus",
            "translation": None,
            "inlier_indices": [],
            "residual_squared": None,
        }
    residual = Fraction(
        sum((tracks[i]["dx"] - dx) ** 2 + (tracks[i]["dy"] - dy) ** 2 for i in inliers),
        len(inliers),
    )
    return {
        "status": "observed",
        "reason": None,
        "translation": [dx, dy],
        "inlier_indices": inliers,
        "residual_squared": residual,
    }


def grid_points(region, radius):
    x, y, w, h = region
    margin = radius + 2
    if min(w, h) < 2 * radius + 10:
        return []
    return [
        (
            x + margin + (2 * col + 1) * (w - 2 * margin) // 12,
            y + margin + (2 * row + 1) * (h - 2 * margin) // 8,
        )
        for row in range(4)
        for col in range(6)
    ]


def estimate_translation(
    first: bytes, second: bytes, width: int, height: int, settings: MotionSettings
) -> dict:
    if (
        not isinstance(first, bytes)
        or not isinstance(second, bytes)
        or len(first) != width * height
        or len(second) != len(first)
    ):
        raise ValueError("Motion buffers do not match analysis geometry")
    region = settings.grid().region(width, height)
    tracks, rejected = [], Counter()
    points = grid_points(region, settings.radius)
    for x, y in points:
        values = patch(first, width, x, y)
        if not textured(values):
            rejected["low_texture"] += 1
            continue
        forward, reason = match(values, second, width, x, y, region, settings.radius)
        if reason:
            rejected[reason] += 1
            continue
        cost, dx, dy = forward
        target_patch = patch(second, width, x + dx, y + dy)
        if not textured(target_patch):
            rejected["low_texture"] += 1
            continue
        backward, reason = match(
            target_patch, first, width, x + dx, y + dy, region, settings.radius
        )
        if reason or backward[1:] != (-dx, -dy):
            rejected["forward_backward"] += 1
            continue
        tracks.append({"x": x, "y": y, "dx": dx, "dy": dy, "sad": cost})
    return {
        "tracks": tracks,
        "rejected": dict(rejected),
        "grid_points": len(points),
        **summarize_tracks(tracks, region),
    }


def path_evidence(pairs: list[dict], time_base: Fraction) -> list[dict]:
    """Independent local runs; never bridge unknown pairs or assume uniform FPS."""
    path, run_start = [0, 0], None
    result = []
    for index, pair in enumerate(pairs):
        if pair["status"] != "observed":
            result.append(
                {
                    "run_start_frame": None,
                    "position": None,
                    "velocity": None,
                    "previous_sample_residual": None,
                    "residual_at_frame": None,
                    "residual_at_pts": None,
                }
            )
            path, run_start = [0, 0], None
            continue
        if run_start is None:
            run_start = pair["from_frame"]
        dx, dy = pair["translation"]
        path = [path[0] + dx, path[1] + dy]
        delta = (pair["to_pts"] - pair["from_pts"]) * time_base
        residual = None
        if index and pairs[index - 1]["status"] == "observed":
            previous = pairs[index - 1]
            before = (previous["to_pts"] - previous["from_pts"]) * time_base
            # Middle path point minus its time-linear interpolation between neighbors.
            residual = [
                (previous["translation"][axis] * delta - pair["translation"][axis] * before)
                / (before + delta)
                for axis in (0, 1)
            ]
        result.append(
            {
                "run_start_frame": run_start,
                "position": list(path),
                "velocity": [Fraction(dx, 1) / delta, Fraction(dy, 1) / delta],
                "previous_sample_residual": residual,
                "residual_at_frame": pair["from_frame"] if residual is not None else None,
                "residual_at_pts": pair["from_pts"] if residual is not None else None,
            }
        )
    return result
