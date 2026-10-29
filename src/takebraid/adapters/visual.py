"""Bounded descriptor decoding and strict source-coordinate record validation."""

from pathlib import Path

from takebraid.adapters.media.quality import decoded_gray
from takebraid.adapters.records import _fraction, read_json
from takebraid.domain.visual import GridDescriptor, describe_gray

MAX_SAMPLES = 1000


def decode_descriptors(context, every):
    width, height = context.geometry
    with decoded_gray(
        context.source,
        context.frame_map,
        context.source_geometry,
        context.geometry,
        timeout=context.inputs["settings"]["timeout"],
    ) as raw:
        rows = []
        for index in range(0, len(context.frame_map.frames), every):
            raw.seek(index * width * height)
            descriptor = describe_gray(raw.read(width * height), width, height)
            rows.append(
                {
                    "frame_index": index,
                    "pts": context.frame_map.frames[index].pts,
                    "values": descriptor.values,
                }
            )
    return rows


def validate_descriptors(path: Path, context, every):
    document = read_json(path, limit=16 * 1024 * 1024)
    expected = "unknown" if context.reasons else "observed"
    if (
        document["inputs"] != context.inputs
        or document["status"] != expected
        or document["reasons"] != context.reasons
        or document["analysis_geometry"] != (list(context.geometry) if context.geometry else None)
    ):
        raise ValueError("Visual descriptor identity/settings/status mismatch; use --force")
    schedule = [] if context.reasons else list(range(0, len(context.frame_map.frames), every))
    rows = document["observations"]
    if not isinstance(rows, list) or len(rows) != len(schedule):
        raise ValueError("Visual descriptor sampling count mismatch")
    for row, index in zip(rows, schedule, strict=True):
        if (
            type(row["frame_index"]) is not int
            or row["frame_index"] != index
            or type(row["pts"]) is not int
            or row["pts"] != context.frame_map.frames[index].pts
            or not isinstance(row["values"], list)
        ):
            raise ValueError("Visual descriptor source coordinates mismatch")
        GridDescriptor(tuple(_fraction(v) for v in row["values"]))
    return document
