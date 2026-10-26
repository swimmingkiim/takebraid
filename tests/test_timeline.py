from fractions import Fraction

import pytest

from takebraid.domain.frames import FrameMap, FrameObservation
from takebraid.domain.time import SourceRange, TimeBase
from takebraid.domain.timeline import SAMPLE_RATE, ManualTimeline, compile_timeline, nearest


def make_source():
    return FrameMap(
        "asset",
        0,
        TimeBase(1, 1000),
        (FrameObservation(-40, 40), FrameObservation(0, 80), FrameObservation(80, 40)),
    )


def test_vfr_source_boundaries_and_cumulative_output_quantization():
    source = make_source()
    cuts = (
        SourceRange("asset", 0, -40, 0, source.time_base),
        SourceRange("asset", 0, 0, 80, source.time_base),
    )
    timeline = ManualTimeline(
        "asset", 0, source.time_base, Fraction(30000, 1001), cuts, "source", 1
    )
    layout = compile_timeline(timeline, source)
    assert [clip.frame_count for clip in layout] == [1, 3]
    assert [clip.start_frame for clip in layout] == [0, 1]
    assert [clip.end_frame for clip in layout] == [1, 2]
    assert sum(clip.sample_count for clip in layout) == nearest(
        Fraction(4 * 1001, 30000) * SAMPLE_RATE
    )
    assert layout[1].audio_start_sample == layout[0].sample_count


def test_many_fractional_cuts_do_not_accumulate_rounding_error():
    source = make_source()
    cut = SourceRange("asset", 0, -40, 0, source.time_base)
    timeline = ManualTimeline(
        "asset", 0, source.time_base, Fraction(30000, 1001), (cut,) * 64, "mute"
    )
    layout = compile_timeline(timeline, source)
    frames = sum(clip.frame_count for clip in layout)
    assert (
        abs(Fraction(frames, 1) / timeline.frame_rate - 64 * cut.duration_seconds)
        <= Fraction(1, 2) / timeline.frame_rate
    )
    assert abs(
        Fraction(sum(c.sample_count for c in layout), SAMPLE_RATE)
        - Fraction(frames, 1) / timeline.frame_rate
    ) <= Fraction(1, 2 * SAMPLE_RATE)


@pytest.mark.parametrize("fps", [Fraction(0), Fraction(121), Fraction(100000, 3333), 25.0])
def test_invalid_output_clocks_are_rejected(fps):
    source = make_source()
    with pytest.raises(ValueError):
        ManualTimeline(
            "asset",
            0,
            source.time_base,
            fps,
            (SourceRange("asset", 0, -40, 0, source.time_base),),
            "mute",
        )


def test_non_boundary_cuts_and_zero_length_output_are_refused():
    source = make_source()
    timeline = ManualTimeline(
        "asset",
        0,
        source.time_base,
        Fraction(25),
        (SourceRange("asset", 0, -39, 0, source.time_base),),
        "mute",
    )
    with pytest.raises(ValueError, match="boundaries"):
        compile_timeline(timeline, source)
    short = ManualTimeline(
        "asset",
        0,
        source.time_base,
        Fraction(1),
        (SourceRange("asset", 0, -40, 0, source.time_base),),
        "mute",
    )
    with pytest.raises(ValueError, match="zero output"):
        compile_timeline(short, source)


@pytest.mark.parametrize(
    "policy,audio",
    [("other", None), ("source", None), ("source", 0), ("source", True), ("mute", 1)],
)
def test_audio_policy_requires_an_explicit_distinct_track(policy, audio):
    source = make_source()
    with pytest.raises((ValueError, TypeError)):
        ManualTimeline(
            "asset",
            0,
            source.time_base,
            Fraction(25),
            (SourceRange("asset", 0, -40, 0, source.time_base),),
            policy,
            audio,
        )
