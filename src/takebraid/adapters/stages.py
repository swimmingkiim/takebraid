"""Content-addressed stage inputs with immutable attempts and validated completion pointers."""

import hashlib
import json
import uuid
from pathlib import Path

from takebraid.adapters.artifacts import replace_json, write_new_json
from takebraid.adapters.identity import file_digest
from takebraid.adapters.projects import project_path
from takebraid.adapters.records import RecordError, read_json


def stage_key(inputs: dict) -> str:
    canonical = json.dumps(
        inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cached_output(root: Path, inputs: dict) -> Path | None:
    key = stage_key(inputs)
    pointer = project_path(root, f"stages/{key}/completed.json")
    if not pointer.exists():
        return None
    receipt = read_json(pointer)
    try:
        if (
            receipt["status"] != "completed"
            or receipt["stage_key"] != key
            or receipt["inputs"] != inputs
            or stage_key(receipt["inputs"]) != key
        ):
            raise RecordError("Invalid completed-stage receipt; use --force to recompute")
        attempt_id = receipt["attempt_id"]
        if (
            not isinstance(attempt_id, str)
            or len(attempt_id) != 32
            or any(character not in "0123456789abcdef" for character in attempt_id)
        ):
            raise RecordError("Invalid attempt identity")
        attempt = root / "stages" / key / "attempts" / attempt_id
        if read_json(attempt / "receipt.json") != receipt:
            raise RecordError("Completed pointer does not match the terminal attempt receipt")
        output = project_path(root, receipt["output"]["path"])
        if not output.is_relative_to(attempt.resolve()):
            raise RecordError("Cached output is outside its attempt")
        if file_digest(output) != receipt["output"]["sha256"]:
            raise RecordError("Cached output checksum mismatch; use --force to recompute")
        return output
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RecordError(f"Cannot reuse stage cache: {exc}") from exc


class StageAttempt:
    def __init__(self, root: Path, inputs: dict):
        self.root = root
        self.inputs = json.loads(json.dumps(inputs, allow_nan=False))
        self.key = stage_key(self.inputs)
        self.directory = root / "stages" / self.key / "attempts" / uuid.uuid4().hex
        self.base = {
            "schema_version": "0.1",
            "stage_key": self.key,
            "inputs": self.inputs,
            "attempt_id": self.directory.name,
        }

    def __enter__(self):
        if not self.directory.resolve().is_relative_to(self.root.resolve()):
            raise RecordError("Stage directory escapes project storage")
        write_new_json(self.directory / "started.json", {**self.base, "status": "running"})
        return self

    def complete(self, output: Path) -> None:
        output = output.resolve()
        if not output.is_relative_to(self.directory.resolve()):
            raise RecordError("Stage output must belong to its attempt directory")
        receipt = {
            **self.base,
            "status": "completed",
            "output": {
                "path": output.relative_to(self.root.resolve()).as_posix(),
                "sha256": file_digest(output),
            },
        }
        write_new_json(self.directory / "receipt.json", receipt)
        replace_json(self.root / "stages" / self.key / "completed.json", receipt)

    def __exit__(self, kind, error, traceback):
        if not (self.directory / "receipt.json").exists():
            state = "cancelled" if kind in (KeyboardInterrupt, SystemExit) else "failed"
            write_new_json(
                self.directory / "receipt.json",
                {
                    **self.base,
                    "status": state,
                    "error_type": kind.__name__ if kind else "IncompleteStage",
                },
            )
        return False


def completed_artifact(root: Path, output: Path) -> dict:
    """Validate a specific preserved attempt, even after a force run advances the pointer."""
    root, output = root.resolve(strict=True), output.resolve(strict=True)
    if not output.is_relative_to(root):
        raise RecordError("Observation must belong to this project")
    receipt = read_json(output.parent / "receipt.json")
    inputs = receipt["inputs"]
    key, identity = stage_key(inputs), receipt["attempt_id"]
    if (
        not isinstance(identity, str)
        or len(identity) != 32
        or any(c not in "0123456789abcdef" for c in identity)
        or output.parent != root / "stages" / key / "attempts" / identity
        or receipt["stage_key"] != key
        or receipt["status"] != "completed"
        or receipt["output"]["path"] != output.relative_to(root).as_posix()
        or receipt["output"]["sha256"] != file_digest(output)
    ):
        raise RecordError("Invalid completed observation artifact/receipt")
    return inputs
