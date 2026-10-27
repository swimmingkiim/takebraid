"""Reversible interval decisions: include all footage except explicit user exclusions."""

from dataclasses import dataclass

from takebraid.domain.frames import FrameMap
from takebraid.domain.time import _require_int

STATES = {"keep", "exclude", "review", "unknown"}
MAX_OVERRIDES = 100


@dataclass(frozen=True)
class DecisionOverride:
    action: str
    state: str | None
    first_frame: int
    end_frame: int
    reason: str

    def __post_init__(self):
        _require_int(self.first_frame, "first frame")
        _require_int(self.end_frame, "end frame")
        if not 0 <= self.first_frame < self.end_frame:
            raise ValueError("Override requires 0 <= FIRST < END")
        if self.action not in {"set", "restore"}:
            raise ValueError("Override action must be set or restore")
        if (self.action == "set" and self.state not in STATES) or (
            self.action == "restore" and self.state is not None
        ):
            raise ValueError("Set requires a decision state; restore reapplies the baseline")
        if not isinstance(self.reason, str) or not self.reason.strip() or len(self.reason) > 1000:
            raise ValueError("A nonempty override reason of at most 1000 characters is required")


def resolve_decisions(
    frame_map: FrameMap, interpretation: dict, overrides: tuple[DecisionOverride, ...]
) -> list[dict]:
    boundaries = frame_map.boundaries()
    cells = interpretation["cells"]
    if len(cells) != len(frame_map.frames):
        raise ValueError("Decision evidence must cover every decoded source frame")
    baseline = []
    for index, cell in enumerate(cells):
        if (cell["in_pts"], cell["out_pts"]) != (boundaries[index], boundaries[index + 1]):
            raise ValueError("Decision evidence boundaries differ from frame map")
        if cell["state"] not in {"unknown", "enter", "hold", "no_trigger"}:
            raise ValueError("Invalid interpretation state")
        baseline.append("unknown" if cell["state"] == "unknown" else "keep")
    indices = {pts: i for i, pts in enumerate(boundaries)}
    for candidate in interpretation["candidates"]:
        first, end = indices[candidate["in_pts"]], indices[candidate["out_pts"]]
        for index in range(first, end):
            if baseline[index] == "unknown":
                raise ValueError("Candidate padding must not cover unknown evidence")
            baseline[index] = "review"
    if not isinstance(overrides, tuple) or len(overrides) > MAX_OVERRIDES:
        raise ValueError("Decision history supports at most 100 overrides")
    states = list(baseline)
    origins = [None] * len(states)
    for number, override in enumerate(overrides):
        if not isinstance(override, DecisionOverride) or override.end_frame > len(states):
            raise ValueError("Override exceeds source frame range")
        for index in range(override.first_frame, override.end_frame):
            states[index] = baseline[index] if override.action == "restore" else override.state
            origins[index] = number
    result = []
    for index, (state, base, origin) in enumerate(zip(states, baseline, origins, strict=True)):
        if result and (
            result[-1]["state"],
            result[-1]["baseline"],
            result[-1]["override_index"],
        ) == (state, base, origin):
            result[-1].update(end_frame=index + 1, out_pts=boundaries[index + 1])
        else:
            result.append(
                {
                    "first_frame": index,
                    "end_frame": index + 1,
                    "in_pts": boundaries[index],
                    "out_pts": boundaries[index + 1],
                    "state": state,
                    "baseline": base,
                    "override_index": origin,
                }
            )
    return result


def included_cuts(intervals: list[dict]) -> tuple[tuple[int, int], ...]:
    cuts = []
    for row in intervals:
        if row["state"] == "exclude":
            continue
        start, end = row["first_frame"], row["end_frame"]
        if cuts and cuts[-1][1] == start:
            cuts[-1] = (cuts[-1][0], end)
        else:
            cuts.append((start, end))
    if not 1 <= len(cuts) <= 64:
        raise ValueError("Decision preview needs 1..64 included runs; empty output is not rendered")
    return tuple(cuts)
