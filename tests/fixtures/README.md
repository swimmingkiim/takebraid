# Fixture provenance

No binary media is committed. `tests/test_media_integration.py` generates a short uniform blue
video (30000/1001 fps, FFV1 in Matroska) and optional 440 Hz sine audio (48 kHz PCM) with FFmpeg's
`color`/`sine` sources in pytest temporary directories. These are synthetic test signals with no
third-party camera footage, people, music or fonts. The generation recipe is project code under
Apache-2.0; the generator binary retains its own license. Files are deleted by test cleanup.

These metadata tests are not the visible-frame-index, irregular-PTS or audio-impulse mapping
fixtures planned in TB-102/TB-105. Rotation, negative starts, unknown values and multiple-stream
metadata are currently exercised with constructed FFprobe JSON in `tests/test_probe.py`.
