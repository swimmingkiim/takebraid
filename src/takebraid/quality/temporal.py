"""Hysteresis and minimum-duration candidates, never exclusion decisions."""

from bisect import bisect_left, bisect_right

from takebraid.domain.interpretation import EvidenceCell, TemporalPolicy
from takebraid.domain.time import TimeBase


def interpret_cells(
    cells: tuple[EvidenceCell, ...], clock: TimeBase, policy: TemporalPolicy
) -> dict:
    if (
        not cells
        or not isinstance(cells, tuple)
        or any(not isinstance(c, EvidenceCell) for c in cells)
    ):
        raise ValueError("Interpretation requires a nonempty tuple of evidence cells")
    if any(a.out_pts != b.in_pts for a, b in zip(cells, cells[1:], strict=False)):
        raise ValueError("Evidence must partition the source range, including unknown cells")
    states = ["unknown"] * len(cells)
    candidates, short_runs = [], []
    index = 0
    while index < len(cells):
        if cells[index].value is None:
            index += 1
            continue
        component_start = index
        while index < len(cells) and cells[index].value is not None:
            index += 1
        component_end = index
        boundaries = [c.in_pts for c in cells[component_start:component_end]] + [
            cells[component_end - 1].out_pts
        ]
        run = None

        def finish(run, end, boundaries):
            if run is None:
                return
            core_in, core_out = cells[run].in_pts, cells[end - 1].out_pts
            duration = clock.seconds(core_out - core_in)
            evidence = [c.evidence_index for c in cells[run:end]]
            if duration < policy.minimum_seconds:
                short_runs.append(
                    {
                        "in_pts": core_in,
                        "out_pts": core_out,
                        "duration_seconds": duration,
                        "evidence_indices": evidence,
                        "reason": "below_minimum_duration",
                    }
                )
                return
            before = core_in - policy.pad_before_seconds / clock.seconds(1)
            after = core_out + policy.pad_after_seconds / clock.seconds(1)
            left = max(0, bisect_right(boundaries, before) - 1)
            right = min(len(boundaries) - 1, bisect_left(boundaries, after))
            candidates.append(
                {
                    "core_in_pts": core_in,
                    "core_out_pts": core_out,
                    "in_pts": boundaries[left],
                    "out_pts": boundaries[right],
                    "duration_seconds": duration,
                    "evidence_indices": evidence,
                    "minimum_value": min(c.value for c in cells[run:end]),
                    "maximum_value": max(c.value for c in cells[run:end]),
                }
            )

        for position in range(component_start, component_end):
            value = cells[position].value
            if run is not None and policy.leaves(value):
                finish(run, position, boundaries)
                run = None
            if run is None and policy.enters(value):
                run = position
                states[position] = "enter"
            elif run is not None:
                states[position] = "hold"
            else:
                states[position] = "no_trigger"
        finish(run, component_end, boundaries)
    observed = sum(c.value is not None for c in cells)
    return {
        "status": "unknown"
        if not observed
        else "partial"
        if observed < len(cells)
        else "interpreted",
        "cells": [
            {
                "in_pts": c.in_pts,
                "out_pts": c.out_pts,
                "value": c.value,
                "evidence_index": c.evidence_index,
                "reason": c.reason,
                "state": state,
            }
            for c, state in zip(cells, states, strict=True)
        ],
        "candidates": candidates,
        "short_runs": short_runs,
    }
