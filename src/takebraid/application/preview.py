"""Persist validated manual cuts and execute a preserved preview stage."""

import math
import uuid
from fractions import Fraction
from pathlib import Path

from takebraid import __version__
from takebraid.adapters.artifacts import write_new_json
from takebraid.adapters.identity import file_digest, signature, verify_source
from takebraid.adapters.media.probe import probe_media
from takebraid.adapters.media.render import ffmpeg_version, render_preview, verify_preview
from takebraid.adapters.projects import asset_source, load_project
from takebraid.adapters.records import load_asset, load_frame_map, read_json
from takebraid.adapters.stages import StageAttempt, cached_output
from takebraid.adapters.timelines import load_timeline
from takebraid.application.scan import scan_asset
from takebraid.domain.time import SourceRange, _require_int
from takebraid.domain.timeline import ManualTimeline, compile_timeline


def create_plan(
    asset_path: Path,
    stream_index: int,
    cuts: tuple[tuple[int, int], ...],
    frame_rate: Fraction,
    audio_policy: str,
    audio_stream_index: int | None,
    *,
    decision_reference: dict | None = None,
) -> Path:
    asset_path = asset_path.expanduser().resolve(strict=True)
    asset = load_asset(asset_path)
    root, _ = asset_source(asset_path, asset)
    project = load_project(root)
    if asset["asset_id"] not in project["assets"]:
        raise ValueError("Register this asset with project add before creating a timeline")
    map_path, _ = scan_asset(asset_path, stream_index)
    frame_map = load_frame_map(map_path)
    boundaries = frame_map.boundaries()
    ranges = []
    for start, end in cuts:
        _require_int(start, "cut start")
        _require_int(end, "cut end")
        if not 0 <= start < end < len(boundaries):
            raise ValueError("Cut indices must satisfy 0 <= FIRST < END <= source frame count")
        ranges.append(
            SourceRange(
                asset["asset_id"],
                stream_index,
                boundaries[start],
                boundaries[end],
                frame_map.time_base,
            )
        )
    timeline = ManualTimeline(
        asset["asset_id"],
        stream_index,
        frame_map.time_base,
        frame_rate,
        tuple(ranges),
        audio_policy,
        audio_stream_index,
    )
    if audio_policy == "source" and not any(
        stream["index"] == audio_stream_index and stream["kind"] == "audio"
        for stream in asset["metadata"]["streams"]
    ):
        raise ValueError("Select an existing source audio stream")
    compile_timeline(timeline, frame_map)
    path = root / "plans" / uuid.uuid4().hex / "timeline.json"
    write_new_json(
        path,
        {
            "schema_version": "0.1",
            "timeline": timeline,
            "asset_metadata_path": asset_path.relative_to(root).as_posix(),
            "frame_map_path": map_path.relative_to(root).as_posix(),
            "frame_map_sha256": file_digest(map_path),
            **(
                {"decision_reference": decision_reference} if decision_reference is not None else {}
            ),
        },
    )
    return path


def render_plan(root: Path, plan_path: Path, *, timeout: float = 300, force: bool = False) -> Path:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Render timeout must be positive and finite")
    root = root.expanduser().resolve(strict=True)
    project = load_project(root)
    plan_path = plan_path.expanduser().resolve(strict=True)
    plan_digest = file_digest(plan_path)
    asset_path, frame_map, timeline = load_timeline(root, plan_path)
    asset = load_asset(asset_path)
    actual_root, source = asset_source(asset_path, asset)
    if (
        actual_root != root
        or asset["asset_id"] != timeline.asset_id
        or asset["asset_id"] not in project["assets"]
    ):
        raise ValueError("Timeline asset does not belong to the selected project")
    before = verify_source(source, asset["source"]["fingerprint"]["digest"])
    active_map_path, _ = scan_asset(asset_path, timeline.stream_index)
    if load_frame_map(active_map_path) != frame_map:
        raise ValueError("Timeline frame evidence differs from verified scan; recreate the plan")
    metadata = probe_media(source)
    if not {"mov", "matroska", "avi", "mpegts", "nut"}.intersection(
        metadata.format_name.split(",")
    ):
        raise ValueError("Preview requires a supported self-contained video container")
    video = next((s for s in metadata.streams if s.index == timeline.stream_index), None)
    if video is None or video.kind != "video":
        raise ValueError("Selected source video stream is unavailable")
    if video.color_transfer in {"smpte2084", "arib-std-b67"}:
        raise ValueError("HDR preview requires an explicit tone-mapping policy (not implemented)")
    if timeline.audio_policy == "source" and not any(
        s.index == timeline.audio_stream_index and s.kind == "audio" for s in metadata.streams
    ):
        raise ValueError("Select an existing source audio stream")
    decision_check = None
    plan_document = read_json(plan_path)
    if "decision_reference" in plan_document:
        from takebraid.application.decisions import validate_decision_plan

        decision_check = validate_decision_plan(
            root, plan_document, asset_path, frame_map, timeline
        )
    clips = compile_timeline(timeline, frame_map)
    inputs = {
        "recipe": "decision-preview/1" if decision_check else "manual-preview/1",
        "plan_sha256": plan_digest,
        "source_sha256": asset["source"]["fingerprint"]["digest"],
        "ffmpeg_version": ffmpeg_version(),
        "ffprobe_version": metadata.ffprobe_version,
        "takebraid_version": __version__,
        "timeout": float(timeout),
    }
    cached = None if force else cached_output(root, inputs)
    if cached is not None:
        verify_preview(cached, timeline, clips)
        if decision_check:
            decision_check()
        if signature(source) != before or file_digest(plan_path) != plan_digest:
            raise ValueError("Source or timeline changed during preview cache validation")
        return cached
    with StageAttempt(root, inputs) as attempt:
        write_new_json(
            attempt.directory / "timeline.json",
            {"schema_version": "0.1", "timeline": timeline, "layout": clips},
        )
        output = render_preview(source, timeline, clips, attempt.directory, timeout=timeout)
        verification = verify_preview(output, timeline, clips)
        if signature(source) != before or file_digest(plan_path) != plan_digest:
            raise ValueError("Source or timeline changed during rendering; preview not certified")
        if decision_check:
            decision_check()
        write_new_json(attempt.directory / "verification.json", verification)
        attempt.complete(output)
        return output
