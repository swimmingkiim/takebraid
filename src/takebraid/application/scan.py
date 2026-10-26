"""Verify a registered source and publish a per-stream decoded frame map."""

import hashlib
import json
import re
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.media.frames import decode_frames
from takebraid.adapters.media.probe import probe_media
from takebraid.domain.frames import FrameMap


class ScanError(ValueError):
    """Asset verification, decode or publication error."""


def scan_asset(
    asset_path: Path, stream_index: int, *, timeout: float = 300, max_frames: int = 250000
) -> tuple[Path, str]:
    try:
        asset_path = asset_path.expanduser().resolve(strict=True)
        if asset_path.stat().st_size > 2 * 1024 * 1024:
            raise ScanError("Asset metadata exceeds the 2 MiB limit")
        document = json.loads(asset_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema_version") != "0.1":
            raise ScanError("Unsupported asset schema; expected version 0.1")
        digest = document["source"]["fingerprint"]["digest"]
        if (
            document["source"]["fingerprint"]["algorithm"] != "sha256"
            or not isinstance(digest, str)
            or not re.fullmatch("[0-9a-f]{64}", digest)
            or document["asset_id"] != f"sha256-{digest}"
        ):
            raise ScanError("Invalid asset content identity")
        source = Path(document["source"]["locator"]).expanduser()
        if not source.is_absolute() or not source.is_file():
            raise ScanError("Asset source must be an existing absolute local file")
        source = source.resolve(strict=True)
        initial = source.stat()
        signature = (
            initial.st_dev,
            initial.st_ino,
            initial.st_size,
            initial.st_mtime_ns,
            initial.st_ctime_ns,
        )
        checksum = hashlib.sha256()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(chunk)
        if checksum.hexdigest() != digest:
            raise ScanError("Source fingerprint changed; ingest the changed media into a new asset")
        metadata = probe_media(source)
        stream = next((s for s in metadata.streams if s.index == stream_index), None)
        if stream is None or stream.kind != "video" or stream.attached_picture:
            raise ScanError("Select a video stream index from asset.json (not audio or cover art)")
        target = asset_path.parent / f"frames-{stream_index}.json"
        if target.exists() or target.is_symlink():
            raise ScanError(f"Frame map already exists: {target}; existing result preserved")
        frames = decode_frames(source, stream_index, timeout=timeout, max_frames=max_frames)
        final = source.stat()
        if signature != (
            final.st_dev,
            final.st_ino,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ):
            raise ScanError("Source changed during frame scan; retry with stable source media")
        frame_map = FrameMap(document["asset_id"], stream_index, stream.time_base, frames)
        write_new_json(
            target,
            {
                "schema_version": "0.1",
                "frame_map": frame_map,
                "status": frame_map.status,
                "issues": frame_map.issues,
                "cadence": frame_map.cadence,
                "presentation_end_pts": frame_map.presentation_end_pts,
                "provenance": {
                    "takebraid_version": __version__,
                    "ffprobe_version": metadata.ffprobe_version,
                    "source_sha256": digest,
                },
            },
        )
        return target, frame_map.status
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ScanError(f"Cannot scan asset: {exc}") from exc
