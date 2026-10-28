import hashlib
from io import BytesIO

import pytest

from tools import labeled_pilot


def configured(monkeypatch, payload=b"source"):
    source = {
        "filename": "source.webm",
        "url": "https://example.invalid/source.webm",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    monkeypatch.setattr(labeled_pilot, "configuration", lambda: ({"sources": [source]}, {}))
    return source


def test_download_is_explicit_checksum_verified_and_existing_source_is_preserved(
    tmp_path, monkeypatch
):
    configured(monkeypatch)
    calls = []

    def response(request, **kwargs):
        calls.append(request.full_url)
        return BytesIO(b"source")

    monkeypatch.setattr(labeled_pilot.urllib.request, "urlopen", response)
    labeled_pilot.fetch(tmp_path)
    labeled_pilot.fetch(tmp_path)
    assert (tmp_path / "source.webm").read_bytes() == b"source"
    assert len(calls) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.webm"]


def test_bad_download_never_publishes_a_corrupt_source(tmp_path, monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr(labeled_pilot.urllib.request, "urlopen", lambda *a, **k: BytesIO(b"wrong"))
    with pytest.raises(ValueError, match="pinned content"):
        labeled_pilot.fetch(tmp_path)
    assert not list(tmp_path.iterdir())


def test_download_cannot_overwrite_changed_existing_source(tmp_path, monkeypatch):
    configured(monkeypatch)
    (tmp_path / "source.webm").write_bytes(b"user file")
    with pytest.raises(ValueError, match="Existing source"):
        labeled_pilot.fetch(tmp_path)
    assert (tmp_path / "source.webm").read_bytes() == b"user file"


def test_review_metadata_never_claims_independent_humans():
    sources, labels = labeled_pilot.configuration()
    assert len(sources["sources"]) == 3
    assert labels["method"] == "assistant_review"
    assert labels["originals"]["mist"]["focus_failure"] == "unknown"
    assert all(s["license"] == "CC0-1.0" for s in sources["sources"])
    assert {s["id"] for s in sources["sources"] if s["split"] == "calibration"} == {"mma"}
    assert all(
        v["first_frame"] == 15 and v["end_frame"] == 35
        for v in labels["controlled_variants"].values()
    )


def locked_fixture(tmp_path):
    import json

    from takebraid.adapters.identity import file_digest

    def write(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return path

    (tmp_path / "clip.mkv").write_bytes(b"fixture")
    write("labels.json", {"version": "fixture"})
    write("sources.json", {"sources": []})
    write(
        "derivations.json",
        {"cases": [{"clip": "clip.mkv", "sha256": file_digest(tmp_path / "clip.mkv")}]},
    )
    write("laplacian_variance-policy.json", {"metric": "laplacian_variance"})
    write("dark_fraction-policy.json", {"metric": "dark_fraction"})
    write(
        "experiment-lock.json",
        {
            f"{name}_sha256": file_digest(tmp_path / f"{name}.json")
            for name in ("labels", "sources", "derivations")
        }
        | {
            "policy_registry": {
                "focus_failure": file_digest(tmp_path / "laplacian_variance-policy.json"),
                "exposure_failure": file_digest(tmp_path / "dark_fraction-policy.json"),
            }
        },
    )
    write("manifest.json", {"dataset_id": "fixture"})
    write(
        "manifest-lock.json",
        {
            "manifest_sha256": file_digest(tmp_path / "manifest.json"),
            "experiment_lock_sha256": file_digest(tmp_path / "experiment-lock.json"),
        },
    )


@pytest.mark.parametrize(
    "name",
    [
        "labels.json",
        "sources.json",
        "derivations.json",
        "dark_fraction-policy.json",
        "manifest.json",
        "clip.mkv",
    ],
)
def test_locked_pilot_rejects_changed_inputs(tmp_path, name):
    locked_fixture(tmp_path)
    labeled_pilot.verify_locked(tmp_path)
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        labeled_pilot.verify_locked(tmp_path)


def test_archive_cannot_write_inside_its_own_dataset(tmp_path):
    locked_fixture(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        labeled_pilot.pack(tmp_path, tmp_path / "self.zip")
