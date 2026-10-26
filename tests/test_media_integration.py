"""Generated test media only; no private or third-party footage is committed."""

import hashlib
import json
import shutil
import subprocess

import pytest

from takebraid.application.ingest import IngestError, ingest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
        reason="media integration requires FFmpeg and ffprobe",
    ),
]


@pytest.mark.parametrize("with_audio", [False, True])
def test_generated_media_ingest(tmp_path, with_audio):
    source = tmp_path / "영상 source ; test.mkv"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=64x48:r=30000/1001:d=0.3",
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.3"]
    command += ["-c:v", "ffv1"]
    if with_audio:
        command += ["-c:a", "pcm_s16le"]
    command += [str(source)]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = ingest(source, tmp_path / "project")
    result = json.loads(output.read_text())
    streams = result["metadata"]["streams"]
    video = next(stream for stream in streams if stream["kind"] == "video")
    assert video["width"] == 64
    assert video["height"] == 48
    assert video["average_frame_rate"] == {"numerator": 30000, "denominator": 1001}
    assert any(stream["kind"] == "audio" for stream in streams) == with_audio
    if with_audio:
        audio = next(stream for stream in streams if stream["kind"] == "audio")
        assert audio["sample_rate"] == 48000
    assert result["source"]["fingerprint"]["digest"] == digest
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest


def test_real_ffprobe_rejects_invalid_media(tmp_path):
    source = tmp_path / "not-video.mov"
    source.write_text("not a video")
    with pytest.raises(IngestError, match="FFprobe could not inspect"):
        ingest(source, tmp_path / "project")
    assert not (tmp_path / "project").exists()
