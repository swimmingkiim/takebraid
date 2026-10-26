# Fixture provenance

No binary media is committed. `tests/test_media_integration.py` generates a short uniform blue
video (30000/1001 fps, FFV1 in Matroska) and optional 440 Hz sine audio (48 kHz PCM) with FFmpeg's
`color`/`sine` sources in pytest temporary directories. These are synthetic test signals with no
third-party camera footage, people, music or fonts. The generation recipe is project code under
Apache-2.0; the generator binary retains its own license. Files are deleted by test cleanup.

`tests/test_frame_integration.py` additionally generates 7-frame MPEG-4/MOV blue video at 25 fps,
with frame selection for irregular timestamps, a two-second PTS offset, and optional B-frames.
The schedules are compared to decoded PTS and the final end. No third-party footage is involved.
Visible-frame-index and audio-impulse rendering fixtures remain TB-105. Rotation, negative starts,
unknown values and multiple-stream
metadata are currently exercised with constructed FFprobe JSON in `tests/test_probe.py`.
