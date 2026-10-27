import copy
import shutil
import struct
import wave
from fractions import Fraction

import pytest

from tools.media_validation.fixtures import COUNT, HEIGHT, WIDTH, write_indexed_inputs
from tools.media_validation.runner import load_cases, run_case, run_matrix


def test_committed_matrix_has_independent_boundary_expectations():
    manifest = load_cases()
    cases = {case["id"]: case for case in manifest["cases"]}
    assert set(cases) == {
        "cfr-reorder",
        "vfr-hold",
        "negative-start",
        "positive-start",
        "ntsc",
        "rotation-90",
        "sar-2",
        "no-audio",
        "delayed-audio",
        "short-audio",
        "b-frames",
        "repeat-64",
        "missing-audio-rejected",
    }
    assert cases["negative-start"]["expected"]["source_pts"][0] == "-2/25"
    assert cases["vfr-hold"]["expected"]["frame_ids"] == [0, 0, 2, 3, 3]
    assert cases["ntsc"]["expected"]["audio_samples"] == 12813
    repeated = cases["repeat-64"]["expected"]
    assert len(repeated["frame_ids"]) == 77
    assert repeated["audio_samples"] == 123323
    assert len(repeated["audio_peaks"]) == 64
    assert all(
        Fraction(value) == 0
        for key, value in manifest["tolerances"].items()
        if key != "gray_absolute"
    )


def test_indexed_signal_is_visible_and_pcm_positions_are_exact(tmp_path):
    raw, audio = write_indexed_inputs(tmp_path, Fraction(30000, 1001))
    pixels = raw.read_bytes()
    assert len(pixels) == COUNT * WIDTH * HEIGHT
    for index in range(COUNT):
        frame = pixels[index * WIDTH * HEIGHT : (index + 1) * WIDTH * HEIGHT]
        assert frame[0] == 16 + index * 16
        assert 255 in frame  # Homemade seven-segment digit, no external font.
    with wave.open(str(audio)) as handle:
        assert handle.getparams()[:3] == (1, 2, 48000)
        assert handle.getnframes() == 12813
        data = handle.readframes(handle.getnframes())
    values = struct.unpack(f"<{len(data) // 2}h", data)
    assert [i for i, sample in enumerate(values) if sample] == [
        100,
        1702,
        3303,
        4905,
        6506,
        8108,
        9710,
        11311,
    ]
    with pytest.raises(FileExistsError):
        write_indexed_inputs(tmp_path)


@pytest.mark.parametrize("selected", [["not-a-case"], ["ntsc", "ntsc"]])
def test_invalid_matrix_selection_does_not_publish_evidence(tmp_path, selected):
    with pytest.raises(ValueError, match="duplicate or unknown"):
        run_matrix(tmp_path / "evidence", selected)
    assert not (tmp_path / "evidence").exists()


def test_existing_fixture_folder_is_never_overwritten(tmp_path):
    manifest = load_cases()
    marker = tmp_path / "keep.txt"
    marker.write_text("original")
    with pytest.raises(FileExistsError):
        run_case(tmp_path, manifest["cases"][0], manifest["tolerances"])
    assert marker.read_text() == "original"


@pytest.mark.integration
@pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requires media tools"
)
def test_wrong_independent_oracle_fails_instead_of_learning_actual_output(tmp_path):
    manifest = load_cases()
    case = copy.deepcopy(manifest["cases"][0])
    case["expected"]["source_pts"][0] = "1/1000"
    result = run_case(tmp_path / "bad-oracle", case, manifest["tolerances"])
    assert result["status"] == "failed"
    assert result["error"] == "Source PTS oracle mismatch"
    assert not list((tmp_path / "bad-oracle").glob("project/plans/*"))
    assert (tmp_path / "bad-oracle/result.json").exists()
