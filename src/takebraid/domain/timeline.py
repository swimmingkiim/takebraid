"""Manual one-source timelines with a shared rational video/audio output clock."""

from dataclasses import dataclass
from fractions import Fraction

from takebraid.domain.frames import FrameMap
from takebraid.domain.time import SourceRange, TimeBase, _require_int

SAMPLE_RATE = 48000


def nearest(value: Fraction) -> int:
    """Round nonnegative output positions, with exact halves rounded up."""
    if value < 0:
        raise ValueError("Output position must be nonnegative")
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


@dataclass(frozen=True)
class ManualTimeline:
    asset_id: str
    stream_index: int
    time_base: TimeBase
    frame_rate: Fraction
    cuts: tuple[SourceRange, ...]
    audio_policy: str
    audio_stream_index: int | None = None

    def __post_init__(self) -> None:
        SourceRange(self.asset_id, self.stream_index, 0, 1, self.time_base)
        if (
            not isinstance(self.frame_rate, Fraction)
            or not 1 <= self.frame_rate <= 120
            or self.frame_rate.numerator > 65535
        ):
            raise ValueError("Preview FPS must be a rational in [1,120] with numerator <=65535")
        if not isinstance(self.cuts, tuple) or not 1 <= len(self.cuts) <= 64:
            raise ValueError("Timeline must contain 1 to 64 cuts")
        for cut in self.cuts:
            if not isinstance(cut, SourceRange) or (
                cut.asset_id,
                cut.stream_index,
                cut.time_base,
            ) != (self.asset_id, self.stream_index, self.time_base):
                raise ValueError("Every cut must reference the same source video stream/clock")
        if self.audio_policy not in {"mute", "source"}:
            raise ValueError("Audio policy must be mute or source")
        if self.audio_policy == "source":
            _require_int(self.audio_stream_index, "audio_stream_index")
            if self.audio_stream_index < 0 or self.audio_stream_index == self.stream_index:
                raise ValueError("Select a distinct nonnegative audio stream index")
        elif self.audio_stream_index is not None:
            raise ValueError("Muted timelines cannot select an audio stream")


@dataclass(frozen=True)
class ClipLayout:
    source: SourceRange
    start_frame: int
    end_frame: int
    output_start_frame: int
    frame_count: int
    audio_start_sample: int
    sample_count: int


def compile_timeline(timeline: ManualTimeline, source: FrameMap) -> tuple[ClipLayout, ...]:
    boundaries = source.boundaries()
    indices = {pts: index for index, pts in enumerate(boundaries)}
    elapsed = Fraction(0)
    output_frames = output_samples = 0
    result = []
    for cut in timeline.cuts:
        source.validate_range(cut)
        elapsed += cut.duration_seconds
        end_frame = nearest(elapsed * timeline.frame_rate)
        end_sample = nearest(Fraction(end_frame, 1) / timeline.frame_rate * SAMPLE_RATE)
        count = end_frame - output_frames
        if count <= 0:
            raise ValueError("A cut rounds to zero output frames; raise FPS or use a longer cut")
        if end_frame > 1000000:
            raise ValueError("Preview exceeds the one-million output frame limit")
        result.append(
            ClipLayout(
                cut,
                indices[cut.in_pts],
                indices[cut.out_pts],
                output_frames,
                count,
                output_samples,
                end_sample - output_samples,
            )
        )
        output_frames, output_samples = end_frame, end_sample
    return tuple(result)
