import json

import pytest

from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.stages import StageAttempt, cached_output, stage_key


def test_stage_keys_are_canonical_and_include_versions_and_settings():
    assert stage_key({"b": 2, "a": 1}) == stage_key({"a": 1, "b": 2})
    baseline = {"source": "a", "recipe": "scan/1", "tool": "1", "settings": {"limit": 5}}
    for name, replacement in [
        ("source", "b"),
        ("recipe", "scan/2"),
        ("tool", "2"),
        ("settings", {"limit": 6}),
    ]:
        assert stage_key({**baseline, name: replacement}) != stage_key(baseline)


def test_only_completed_intact_output_is_reusable(tmp_path):
    inputs = {"recipe": "test/1"}
    with StageAttempt(tmp_path, inputs) as attempt:
        assert cached_output(tmp_path, inputs) is None
        output = attempt.directory / "output.json"
        write_new_json(output, {"schema_version": "0.1", "value": 1})
        attempt.complete(output)
    assert cached_output(tmp_path, inputs) == output
    output.write_text("changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        cached_output(tmp_path, inputs)


@pytest.mark.parametrize(
    "failure,status", [(RuntimeError("failure"), "failed"), (KeyboardInterrupt(), "cancelled")]
)
def test_failure_or_cancellation_never_becomes_a_cache_hit(tmp_path, failure, status):
    inputs = {"recipe": "test/1"}
    with pytest.raises(type(failure)), StageAttempt(tmp_path, inputs) as attempt:
        raise failure
    assert json.loads((attempt.directory / "receipt.json").read_text())["status"] == status
    assert cached_output(tmp_path, inputs) is None


def test_missing_terminal_receipt_invalidates_completion_pointer(tmp_path):
    inputs = {"recipe": "test/1"}
    with StageAttempt(tmp_path, inputs) as attempt:
        output = attempt.directory / "output.json"
        write_new_json(output, {"schema_version": "0.1"})
        attempt.complete(output)
    (attempt.directory / "receipt.json").unlink()
    with pytest.raises(ValueError):
        cached_output(tmp_path, inputs)
