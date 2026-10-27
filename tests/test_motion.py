import json
import random
from dataclasses import replace
from fractions import Fraction

import pytest

from takebraid.application.ingest import ingest
from takebraid.application.motion import observe_motion
from takebraid.cli import main
from takebraid.domain.frames import FrameObservation
from takebraid.domain.motion import MotionSettings
from takebraid.quality.motion import estimate_translation, path_evidence, summarize_tracks
from tools.motion_fixtures import sequence, texture


@pytest.mark.parametrize("translation", [(0, 0), (2, -1), (-2, 2)])
def test_known_integer_translation_is_observed(translation):
    result = estimate_translation(texture(), texture(shift=translation), 96, 64, MotionSettings())
    assert result["status"] == "observed"
    assert result["translation"] == list(translation)
    assert len(result["tracks"]) == len(result["inlier_indices"]) == 24
    assert result["residual_squared"] == 0


def test_independently_moving_foreground_does_not_override_distributed_background():
    first, second = bytearray(texture()), bytearray(texture())
    subject = random.Random(89).randbytes(24 * 18)
    for data, dx in ((first, 0), (second, 2)):
        for y in range(18):
            data[(12 + y) * 96 + 8 + dx : (12 + y) * 96 + 32 + dx] = subject[y * 24 : (y + 1) * 24]
    result = estimate_translation(bytes(first), bytes(second), 96, 64, MotionSettings())
    assert result["status"] == "observed"
    assert result["translation"] == [0, 0]
    assert any(t["dx"] == 2 for t in result["tracks"])
    assert len(result["inlier_indices"]) < len(result["tracks"])


@pytest.mark.parametrize("kind", ["flat", "repeated", "occluded", "boundary"])
def test_unreliable_correspondences_are_unknown_not_zero_motion(kind):
    first, second = texture(), texture()
    if kind == "flat":
        first = second = bytes([128]) * (96 * 64)
    elif kind == "repeated":
        first = second = bytes((x % 2) * 255 for y in range(64) for x in range(96))
    elif kind == "occluded":
        second = texture(seed=99)
    else:
        second = texture(shift=(4, 0))
    result = estimate_translation(first, second, 96, 64, MotionSettings())
    assert result["status"] == "unknown"
    assert result["translation"] is result["residual_squared"] is None
    assert len(result["tracks"]) + sum(result["rejected"].values()) == 24


def test_competing_or_localized_tracks_do_not_certify_a_background_model():
    tracks = [
        {"x": 10 + x * 14, "y": 10 + y * 14, "dx": x % 2, "dy": 0, "sad": 0}
        for y in range(4)
        for x in range(6)
    ]
    assert summarize_tracks(tracks, (0, 0, 96, 64))["reason"] == "ambiguous_consensus"
    for t in tracks:
        t.update(dx=0, x=10, y=10)
    assert summarize_tracks(tracks, (0, 0, 96, 64))["reason"] == "insufficient_spatial_consensus"


def test_path_residual_uses_actual_time_and_resets_after_unknown():
    pairs = [
        {
            "status": "observed",
            "translation": [1, 0],
            "from_frame": 0,
            "from_pts": -10,
            "to_pts": 0,
        },
        {"status": "observed", "translation": [2, 0], "from_frame": 1, "from_pts": 0, "to_pts": 20},
        {"status": "unknown"},
        {
            "status": "observed",
            "translation": [-1, 0],
            "from_frame": 3,
            "from_pts": 30,
            "to_pts": 40,
        },
    ]
    path = path_evidence(pairs, Fraction(1, 10))
    assert path[1]["position"] == [3, 0]
    assert path[1]["velocity"] == [1, 0]
    assert path[1]["previous_sample_residual"] == [0, 0]
    assert path[2]["position"] is None
    assert path[3]["run_start_frame"] == 3
    assert path[3]["position"] == [-1, 0]
    assert path[3]["previous_sample_residual"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size": 31},
        {"size": 193},
        {"radius": 0},
        {"radius": True},
        {"every": 0},
        {"background": (0, 0, 10, 10)},
    ],
)
def test_invalid_motion_settings_are_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        MotionSettings(**kwargs)


@pytest.fixture
def registered(tmp_path, monkeypatch, probe_metadata):
    source = tmp_path / "source ; name.mkv"
    source.write_bytes(b"synthetic motion source")
    metadata = replace(
        probe_metadata,
        format_name="matroska",
        streams=(
            replace(
                probe_metadata.streams[0],
                width=96,
                height=64,
                pixel_format="gray",
            ),
        ),
    )
    for module in ("ingest", "scan", "analysis"):
        monkeypatch.setattr(f"takebraid.application.{module}.probe_media", lambda _: metadata)
    monkeypatch.setattr(
        "takebraid.application.scan.decode_frames",
        lambda *a, **k: (
            FrameObservation(-40, 40),
            FrameObservation(0, 40),
            FrameObservation(40, 40),
        ),
    )
    monkeypatch.setattr("takebraid.application.analysis.analysis_tools", lambda: {"ffmpeg": "fake"})

    def decode(source, frame_map, source_geometry, geometry, settings, **kwargs):
        indices = list(range(0, 3, settings.every))
        return [
            {
                "from_frame": a,
                "to_frame": b,
                "from_pts": frame_map.frames[a].pts,
                "to_pts": frame_map.frames[b].pts,
                **estimate_translation(
                    texture(shift=(a, 0)), texture(shift=(b, 0)), 96, 64, settings
                ),
            }
            for a, b in zip(indices, indices[1:], strict=False)
        ]

    monkeypatch.setattr("takebraid.application.motion.decode_motion", decode)
    return ingest(source, tmp_path / "project"), source, metadata


def test_motion_cache_settings_force_and_source_preservation(registered):
    asset, source, _ = registered
    before = source.read_bytes()
    first, status = observe_motion(asset, 0)
    assert status == "observed"
    assert observe_motion(asset, 0)[0] == first
    forced, _ = observe_motion(asset, 0, force=True)
    sampled, _ = observe_motion(asset, 0, MotionSettings(every=2))
    assert first != forced != sampled
    assert first.exists() and source.read_bytes() == before
    rows = json.loads(sampled.read_text())["pairs"]
    assert [(r["from_pts"], r["to_pts"]) for r in rows] == [(-40, 40)]
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="fingerprint"):
        observe_motion(asset, 0)


def test_unknown_hdr_and_cli_exit(registered, monkeypatch):
    asset, _, metadata = registered
    metadata = replace(
        metadata, streams=(replace(metadata.streams[0], color_transfer="smpte2084"),)
    )
    monkeypatch.setattr("takebraid.application.analysis.probe_media", lambda _: metadata)
    path, status = observe_motion(asset, 0)
    assert status == "unknown"
    assert json.loads(path.read_text())["pairs"] == []
    assert main(["motion", str(asset), "--stream", "0"]) == 2


@pytest.mark.parametrize(
    "error,state", [(ValueError("failed"), "failed"), (KeyboardInterrupt(), "cancelled")]
)
def test_motion_failure_cancellation_and_mutation_preserve_receipts(
    registered, monkeypatch, error, state
):
    asset, _, _ = registered

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("takebraid.application.motion.decode_motion", fail)
    with pytest.raises(type(error)):
        observe_motion(asset, 0)
    receipts = [
        json.loads(p.read_text()) for p in asset.parents[2].glob("stages/*/attempts/*/receipt.json")
    ]
    assert any(
        r["status"] == state and r["inputs"]["recipe"] == "background-translation/1"
        for r in receipts
    )


def test_motion_source_change_and_corrupt_cache_are_rejected(registered, monkeypatch):
    asset, source, _ = registered
    path, _ = observe_motion(asset, 0)
    path.write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        observe_motion(asset, 0)

    def mutate(*args, **kwargs):
        source.write_bytes(b"changed")
        return []

    monkeypatch.setattr("takebraid.application.motion.decode_motion", mutate)
    with pytest.raises(ValueError, match="changed during"):
        observe_motion(asset, 0, force=True)


def test_explicit_background_region_can_exclude_a_large_moving_subject():
    frames = sequence("majority-subject")
    result = estimate_translation(
        frames[0], frames[1], 96, 64, MotionSettings(background=(64, 0, 32, 64))
    )
    assert result["status"] == "observed"
    assert result["translation"] == [0, 0]


def test_loader_recomputes_consensus_and_path(registered, tmp_path):
    from takebraid.adapters.motion import validate_motion
    from takebraid.adapters.records import load_frame_map
    from takebraid.application.scan import scan_asset

    asset, _, _ = registered
    output, _ = observe_motion(asset, 0)
    original = json.loads(output.read_text())
    frame_map = load_frame_map(scan_asset(asset, 0)[0])
    for change in ("pts", "track", "summary", "path", "status"):
        document = json.loads(output.read_text())
        if change == "pts":
            document["pairs"][0]["from_pts"] = 999
        elif change == "track":
            document["pairs"][0]["tracks"][0]["dx"] = 100
        elif change == "summary":
            document["pairs"][0]["translation"] = [0, 0]
        elif change == "path":
            document["path"][0]["position"] = [100, 100]
        else:
            document["status"] = "unknown"
        target = tmp_path / f"bad-motion-{change}.json"
        target.write_text(json.dumps(document))
        with pytest.raises(ValueError):
            validate_motion(target, original["inputs"], frame_map, MotionSettings(), (96, 64), [])


def test_motion_cli_bad_arguments_and_cancellation(monkeypatch, capsys):
    assert main(["motion", "asset.json", "--stream", "0", "--radius", "0"]) == 1
    assert "search radius" in capsys.readouterr().err

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("takebraid.cli.observe_motion", cancel)
    assert main(["motion", "asset.json", "--stream", "0"]) == 130
    assert "cancelled" in capsys.readouterr().err


def test_only_a_textured_moving_subject_on_flat_background_is_unknown():
    first, second = bytearray([128]) * (96 * 64), bytearray([128]) * (96 * 64)
    subject = random.Random(11).randbytes(24 * 18)
    for data, dx in ((first, 0), (second, 2)):
        for y in range(18):
            data[(12 + y) * 96 + 8 + dx : (12 + y) * 96 + 32 + dx] = subject[y * 24 : (y + 1) * 24]
    result = estimate_translation(bytes(first), bytes(second), 96, 64, MotionSettings())
    assert result["status"] == "unknown"
    assert result["translation"] is None


def test_unknown_pair_breaks_path_and_marks_partial_report(registered, monkeypatch):
    from takebraid.application import motion

    asset, _, _ = registered
    original = motion.decode_motion

    def one_unknown(*args, **kwargs):
        pairs = original(*args, **kwargs)
        pairs[1].update(
            estimate_translation(bytes(96 * 64), bytes(96 * 64), 96, 64, MotionSettings())
        )
        return pairs

    monkeypatch.setattr(motion, "decode_motion", one_unknown)
    path, status = observe_motion(asset, 0)
    assert status == "partial"
    assert json.loads(path.read_text())["path"][1]["position"] is None
    assert main(["motion", str(asset), "--stream", "0"]) == 2
