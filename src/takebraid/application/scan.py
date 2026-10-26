"""Verify source media, reuse validated stage output, or publish a new attempt."""

from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.identity import signature, verify_source
from takebraid.adapters.media.frames import decode_frames
from takebraid.adapters.media.probe import probe_media
from takebraid.adapters.projects import asset_source
from takebraid.adapters.records import load_asset, load_frame_map
from takebraid.adapters.stages import StageAttempt, cached_output
from takebraid.domain.frames import FrameMap


class ScanError(ValueError):
    """Asset verification, decode or publication error."""


def scan_asset(
    asset_path: Path,
    stream_index: int,
    *,
    timeout: float = 300,
    max_frames: int = 250000,
    force: bool = False,
) -> tuple[Path, str]:
    try:
        asset_path = asset_path.expanduser().resolve(strict=True)
        document = load_asset(asset_path)
        root, source = asset_source(asset_path, document)
        digest = document["source"]["fingerprint"]["digest"]
        before = verify_source(source, digest)
        metadata = probe_media(source)
        stream = next((s for s in metadata.streams if s.index == stream_index), None)
        if stream is None or stream.kind != "video" or stream.attached_picture:
            raise ScanError("Select a video stream index from asset.json (not audio or cover art)")
        inputs = {
            "recipe": "frame-scan/1",
            "source_sha256": digest,
            "takebraid_version": __version__,
            "ffprobe_version": metadata.ffprobe_version,
            "settings": {
                "stream_index": stream_index,
                "timeout": float(timeout),
                "max_frames": max_frames,
            },
        }
        cached = None if force else cached_output(root, inputs)
        if cached is not None:
            result = load_frame_map(cached)
            if (
                result.asset_id != document["asset_id"]
                or result.stream_index != stream_index
                or result.time_base != stream.time_base
            ):
                raise ScanError("Cached frame map has the wrong source identity/clock; use --force")
            if before != signature(source):
                raise ScanError("Source changed during cache verification")
            return cached, result.status
        with StageAttempt(root, inputs) as attempt:
            frames = decode_frames(source, stream_index, timeout=timeout, max_frames=max_frames)
            if before != signature(source):
                raise ScanError("Source changed during frame scan; retry with stable source media")
            result = FrameMap(document["asset_id"], stream_index, stream.time_base, frames)
            target = attempt.directory / "frames.json"
            write_new_json(
                target,
                {
                    "schema_version": "0.1",
                    "frame_map": result,
                    "status": result.status,
                    "issues": result.issues,
                    "cadence": result.cadence,
                    "presentation_end_pts": result.presentation_end_pts,
                    "provenance": {
                        "takebraid_version": __version__,
                        "ffprobe_version": metadata.ffprobe_version,
                        "source_sha256": digest,
                    },
                },
            )
            load_frame_map(target)
            attempt.complete(target)
            return target, result.status
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ScanError(f"Cannot scan asset: {exc}") from exc
