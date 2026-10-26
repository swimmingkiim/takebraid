"""Register one read-only local video and persist its metadata observations."""

import hashlib
from os import stat_result
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.media.probe import ProbeError, probe_media
from takebraid.adapters.projects import register_asset


class IngestError(ValueError):
    """A source or project error suitable for display at the CLI boundary."""


def _signature(stat: stat_result) -> tuple[int, int, int, int, int]:
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def ingest(source: Path, project: Path) -> Path:
    """Save assets/<content-id>/asset.json; never overwrite metadata or source."""
    try:
        source = source.expanduser().resolve(strict=True)
        if not source.is_file():
            raise IngestError("Source must be a regular local video file")
        project = project.expanduser().resolve()
        if project.exists() and not project.is_dir():
            raise IngestError("Project output must be a directory")
        initial = source.stat()
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if _signature(initial) != _signature(source.stat()):
            raise IngestError("Source changed while hashing; retry with a stable source file")
        content_hash = digest.hexdigest()
        asset_id = f"sha256-{content_hash}"
        target = project / "assets" / asset_id / "asset.json"
        # Check early, then no-clobber publication also protects concurrent calls.
        if target.exists() or target.is_symlink():
            raise IngestError(
                f"Asset already registered: {target}; existing metadata was preserved"
            )
        metadata = probe_media(source)
        if _signature(initial) != _signature(source.stat()):
            raise IngestError("Source changed during inspection; retry with a stable source file")
        document = {
            "schema_version": "0.1",
            "asset_id": asset_id,
            "source": {
                "locator": str(source),
                "size_bytes": initial.st_size,
                "mtime_ns": initial.st_mtime_ns,
                "fingerprint": {"algorithm": "sha256", "digest": content_hash},
            },
            "metadata": metadata,
            "provenance": {"takebraid_version": __version__},
            "timing_status": "metadata_only_unverified_frame_timestamps",
        }
        # Even a malicious destination symlink must not replace source media.
        if target.resolve() == source:
            raise IngestError("Metadata destination cannot be the source file")
        write_new_json(target, document)
        register_asset(project, target)
        return target
    except (OSError, ProbeError, ValueError) as exc:
        raise IngestError(f"Cannot ingest {source}: {exc}") from exc
