"""Atomic publication of new metadata, without replacing an existing file."""

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from fractions import Fraction
from pathlib import Path


def to_json_value(value: object) -> object:
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if is_dataclass(value) and not isinstance(value, type):
        return to_json_value(asdict(value))
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    return value


def write_new_json(target: Path, document: dict) -> None:
    """Publish a fully flushed file using a same-filesystem, no-clobber hard link.

    The project filesystem must support hard links. A failed write leaves existing
    metadata untouched. Directory fsync / power-loss durability is not promised.
    """
    payload = json.dumps(to_json_value(document), ensure_ascii=False, indent=2, allow_nan=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=".asset-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
