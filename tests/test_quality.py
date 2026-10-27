import json
from dataclasses import replace
from fractions import Fraction

import pytest

from takebraid.adapters.media.quality import check_decode_log
from takebraid.application.ingest import ingest
from takebraid.application.quality import observe_quality
from takebraid.cli import main
from takebraid.domain.frames import FrameMap, FrameObservation
from takebraid.domain.quality import QualitySettings
from takebraid.domain.time import TimeBase
from takebraid.quality.metrics import measure_gray


def test_uniform_exposure_and_focus_metrics_are_exact():
    settings = QualitySettings()
    black = measure_gray(bytes(25), 5, 5, settings)
    white = measure_gray(bytes([255]) * 25, 5, 5, settings)
    middle = measure_gray(bytes([128]) * 25, 5, 5, settings)
    assert black.mean_luma == black.laplacian_variance == 0
    assert black.dark_fraction == 1
    assert white.mean_luma == white.bright_fraction == 1
    assert white.luma_variance == white.laplacian_variance == 0
    assert middle.mean_luma == Fraction(128, 255)
    assert middle.dark_fraction == middle.bright_fraction == 0


def test_laplacian_variance_and_roi_have_independent_hand_calculated_oracle():
    # Nine interior pixels: one -4 and four +1 responses, divided by 255 before variance.
    pixels = bytearray(25)
    pixels[12] = 255
    result = measure_gray(bytes(pixels), 5, 5, QualitySettings())
    assert result.laplacian_variance == Fraction(20, 9)
    assert result.mean_luma == Fraction(1, 25)
    assert result.luma_variance == Fraction(24, 625)
    assert result.dark_fraction == Fraction(24, 25)
    assert result.bright_fraction == Fraction(1, 25)
    # Select a flat region and exclude the bright last column.
    raw = bytes([128, 128, 128, 255] * 4)
    roi = measure_gray(raw, 4, 4, QualitySettings(roi=(0, 0, 3, 4)))
    assert roi.mean_luma == Fraction(128, 255)
    assert roi.laplacian_variance == roi.bright_fraction == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size": 15},
        {"size": 513},
        {"size": True},
        {"every": 0},
        {"every": False},
        {"roi": (0, 0, 2, 3)},
        {"roi": (-1, 0, 3, 3)},
        {"roi": (0, 0, 3)},
    ],
)
def test_invalid_settings_are_rejected(kwargs):
    with pytest.raises((TypeError, ValueError)):
        QualitySettings(**kwargs)


def test_analysis_scale_is_bounded_without_upscaling():
    assert QualitySettings().geometry(1920, 1080) == (160, 90)
    assert QualitySettings().geometry(64, 48) == (64, 48)
    assert QualitySettings().geometry(1080, 1920) == (90, 160)
    with pytest.raises(ValueError, match="exceeds"):
        QualitySettings(roi=(63, 0, 3, 3)).geometry(64, 48)


def test_decode_log_requires_actual_source_pts_and_progressive_geometry():
    frame_map = FrameMap("asset", 0, TimeBase(1, 1000), (FrameObservation(-40, 40),))
    lines = [
        "[Parsed_showinfo_0] config in time_base: 1/1000, frame_rate: 25/1",
        "[Parsed_showinfo_0] n: 0 pts: -40 pts_time:-0.04 fmt:gray sar:1/1 s:5x5 i:P iskey:1",
    ]
    check_decode_log(lines, frame_map, (5, 5))
    for altered in [
        [lines[0], lines[1].replace("pts: -40", "pts: 0")],
        [lines[0], lines[1].replace("i:P", "i:T")],
        [lines[0], lines[1].replace("5x5", "6x5")],
        lines[:1],
        [*lines, "[error] corrupted frame"],
    ]:
        with pytest.raises(ValueError):
            check_decode_log(altered, frame_map, (5, 5))


@pytest.fixture
def registered(tmp_path, monkeypatch, probe_metadata):
    source = tmp_path / "source ; name.mkv"
    source.write_bytes(b"synthetic")
    metadata = replace(
        probe_metadata,
        format_name="matroska",
        streams=(
            replace(
                probe_metadata.streams[0],
                width=5,
                height=5,
                pixel_format="gray",
            ),
        ),
    )
    for module in ("ingest", "scan", "quality"):
        monkeypatch.setattr(f"takebraid.application.{module}.probe_media", lambda _: metadata)
    monkeypatch.setattr(
        "takebraid.application.scan.decode_frames",
        lambda *a, **k: (
            FrameObservation(-40, 40),
            FrameObservation(0, 40),
        ),
    )
    monkeypatch.setattr("takebraid.application.quality.analysis_tools", lambda: {"ffmpeg": "fake"})

    def decode(source, frame_map, source_geometry, geometry, settings, **kwargs):
        return [
            {
                "frame_index": i,
                "pts": frame_map.frames[i].pts,
                "metrics": measure_gray(bytes([128]) * 25, 5, 5, settings),
            }
            for i in range(0, 2, settings.every)
        ]

    monkeypatch.setattr("takebraid.application.quality.decode_measurements", decode)
    return ingest(source, tmp_path / "project"), source, metadata


def test_observations_are_cached_force_preserves_and_settings_invalidate(registered):
    asset, source, _ = registered
    original = source.read_bytes()
    first, status = observe_quality(asset, 0)
    assert status == "observed"
    assert observe_quality(asset, 0)[0] == first
    forced, _ = observe_quality(asset, 0, force=True)
    sampled, _ = observe_quality(asset, 0, QualitySettings(every=2))
    assert first != forced != sampled
    assert first.exists()
    data = json.loads(sampled.read_text())
    assert [r["pts"] for r in data["observations"]] == [-40]
    assert source.read_bytes() == original
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="fingerprint changed"):
        observe_quality(asset, 0)


def test_unsupported_declared_color_is_unknown_not_good(registered, monkeypatch):
    asset, _, metadata = registered
    metadata = replace(
        metadata, streams=(replace(metadata.streams[0], color_transfer="smpte2084"),)
    )
    monkeypatch.setattr("takebraid.application.quality.probe_media", lambda _: metadata)
    output, status = observe_quality(asset, 0)
    assert status == "unknown"
    data = json.loads(output.read_text())
    assert data["reasons"] == ["hdr_or_wide_gamut_not_supported"]
    assert data["observations"] == []
    assert main(["quality", str(asset), "--stream", "0"]) == 2


def test_changed_cache_is_rejected(registered):
    asset, _, _ = registered
    output, _ = observe_quality(asset, 0)
    output.write_text("{}")
    with pytest.raises(ValueError, match="checksum mismatch"):
        observe_quality(asset, 0)


@pytest.mark.parametrize(
    "error,state", [(ValueError("decode failed"), "failed"), (KeyboardInterrupt(), "cancelled")]
)
def test_decode_failure_and_cancellation_are_preserved(registered, monkeypatch, error, state):
    asset, _, _ = registered

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("takebraid.application.quality.decode_measurements", fail)
    with pytest.raises(type(error)):
        observe_quality(asset, 0)
    receipts = [
        json.loads(p.read_text()) for p in asset.parents[2].glob("stages/*/attempts/*/receipt.json")
    ]
    assert any(
        r["status"] == state and r["inputs"]["recipe"] == "focus-exposure/1" for r in receipts
    )


def test_source_mutation_during_measurement_cannot_be_certified(registered, monkeypatch):
    asset, source, _ = registered

    def mutate(*args, **kwargs):
        source.write_bytes(b"mutated")
        return []

    monkeypatch.setattr("takebraid.application.quality.decode_measurements", mutate)
    with pytest.raises(ValueError, match="changed during"):
        observe_quality(asset, 0)


def test_loader_revalidates_coordinates_metrics_and_status(registered, tmp_path):
    from takebraid.adapters.quality import validate_observations
    from takebraid.adapters.records import load_frame_map
    from takebraid.application.scan import scan_asset

    asset, _, _ = registered
    output, _ = observe_quality(asset, 0)
    original = json.loads(output.read_text())
    frame_map = load_frame_map(scan_asset(asset, 0)[0])
    for change in ("pts", "metric", "status"):
        document = json.loads(output.read_text())
        if change == "pts":
            document["observations"][0]["pts"] = 999
        elif change == "metric":
            document["observations"][0]["metrics"]["mean_luma"] = {"numerator": 2, "denominator": 1}
        else:
            document["status"] = "unknown"
        target = tmp_path / f"bad-{change}.json"
        target.write_text(json.dumps(document))
        with pytest.raises(ValueError):
            validate_observations(
                target, original["inputs"], frame_map, QualitySettings(), (5, 5), []
            )


def test_cli_cancellation_and_bad_roi_are_actionable(monkeypatch, capsys):
    def cancel(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("takebraid.cli.observe_quality", cancel)
    assert main(["quality", "asset.json", "--stream", "0"]) == 130
    assert "cancelled" in capsys.readouterr().err
    assert main(["quality", "asset.json", "--stream", "0", "--roi", "0:0:2:2"]) == 1
    assert "at least 3" in capsys.readouterr().err
