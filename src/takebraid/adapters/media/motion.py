"""Sample verified grayscale frames without retaining an entire clip in memory."""

from pathlib import Path

from takebraid.adapters.media.quality import decoded_gray
from takebraid.domain.frames import FrameMap
from takebraid.domain.motion import MotionSettings
from takebraid.quality.motion import estimate_translation

MAX_PAIRS = 500


def decode_motion(
    source: Path,
    frame_map: FrameMap,
    source_geometry: tuple[int, int],
    geometry: tuple[int, int],
    settings: MotionSettings,
    *,
    timeout: float,
) -> list[dict]:
    schedule = list(range(0, len(frame_map.frames), settings.every))
    if len(schedule) - 1 > MAX_PAIRS:
        raise ValueError("Motion analysis exceeds 500 pair budget; increase --every")
    width, height = geometry
    stride = width * height
    pairs = []
    with decoded_gray(source, frame_map, source_geometry, geometry, timeout=timeout) as raw:
        previous, previous_index = None, None
        for index in schedule:
            raw.seek(index * stride)
            pixels = raw.read(stride)
            if previous is not None:
                pairs.append(
                    {
                        "from_frame": previous_index,
                        "to_frame": index,
                        "from_pts": frame_map.frames[previous_index].pts,
                        "to_pts": frame_map.frames[index].pts,
                        **estimate_translation(previous, pixels, width, height, settings),
                    }
                )
            previous, previous_index = pixels, index
    return pairs
