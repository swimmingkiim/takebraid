"""Versioned timeline documents resolve only project-contained metadata/evidence."""

from pathlib import Path

from takebraid.adapters.identity import file_digest
from takebraid.adapters.projects import project_path
from takebraid.adapters.records import RecordError, _clock, _fraction, load_frame_map, read_json
from takebraid.domain.time import SourceRange
from takebraid.domain.timeline import ManualTimeline, compile_timeline


def load_timeline(root: Path, path: Path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(root.resolve()):
        raise RecordError("Timeline must be inside the selected project")
    document = read_json(path)
    try:
        asset_path = project_path(root, document["asset_metadata_path"])
        map_path = project_path(root, document["frame_map_path"])
        if file_digest(map_path) != document["frame_map_sha256"]:
            raise RecordError("Timeline's source frame-map checksum changed")
        raw = document["timeline"]
        clock = _clock(raw["time_base"])
        timeline = ManualTimeline(
            raw["asset_id"],
            raw["stream_index"],
            clock,
            _fraction(raw["frame_rate"]),
            tuple(
                SourceRange(
                    cut["asset_id"],
                    cut["stream_index"],
                    cut["in_pts"],
                    cut["out_pts"],
                    _clock(cut["time_base"]),
                )
                for cut in raw["cuts"]
            ),
            raw["audio_policy"],
            raw["audio_stream_index"],
        )
        source_map = load_frame_map(map_path)
        compile_timeline(timeline, source_map)
        return asset_path, source_map, timeline
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RecordError(f"Invalid manual timeline: {exc}") from exc
