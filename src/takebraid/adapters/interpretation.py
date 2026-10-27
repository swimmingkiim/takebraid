"""Strict explicit-policy records and source-clock evidence conversion."""

import re
from dataclasses import fields
from fractions import Fraction
from pathlib import Path

from takebraid.adapters.records import _fraction, read_json
from takebraid.domain.frames import FrameMap
from takebraid.domain.interpretation import EvidenceCell, TemporalPolicy


def load_policy(path: Path) -> TemporalPolicy:
    document = read_json(path, limit=65536)
    expected = {f.name for f in fields(TemporalPolicy)} | {"schema_version"}
    if set(document) != expected:
        raise ValueError("Policy fields must exactly match the temporal policy schema")
    values = {}
    for name in expected - {"schema_version", "name", "calibration", "metric"}:
        raw = document[name]
        if not isinstance(raw, str) or not re.fullmatch(
            r"[0-9]{1,16}(?:/[0-9]{1,10}|\.[0-9]{1,9})?", raw
        ):
            raise ValueError("Policy numbers must be short rational strings, e.g. '1/10'")
        values[name] = Fraction(raw)
    return TemporalPolicy(document["name"], document["calibration"], document["metric"], **values)


def evidence_cells(
    document: dict, frame_map: FrameMap, policy: TemporalPolicy
) -> tuple[EvidenceCell, ...]:
    boundaries = frame_map.boundaries()
    measured = {}
    if policy.source_kind == "quality":
        for index, row in enumerate(document["observations"]):
            measured[row["frame_index"]] = (_fraction(row["metrics"][policy.metric]), index)
        missing_reason = "unmeasured_or_unsupported"
    else:
        missing_reason = "unmeasured_or_unreliable_path"
        if document["model_role"] != "declared_background_translation":
            missing_reason = "background_not_declared"
        else:
            for index, row in enumerate(document["path"]):
                if row["previous_sample_residual"] is not None:
                    dx, dy = (_fraction(v) for v in row["previous_sample_residual"])
                    measured[row["residual_at_frame"]] = (dx * dx + dy * dy, index)
    return tuple(
        EvidenceCell(start, end, *measured[index])
        if index in measured
        else EvidenceCell(start, end, None, None, missing_reason)
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False))
    )
