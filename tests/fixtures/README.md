# Fixture provenance

No binary media is committed. `tests/test_media_integration.py` generates a short uniform blue
video (30000/1001 fps, FFV1 in Matroska) and optional 440 Hz sine audio (48 kHz PCM) with FFmpeg's
`color`/`sine` sources in pytest temporary directories. These are synthetic test signals with no
third-party camera footage, people, music or fonts. The generation recipe is project code under
Apache-2.0; the generator binary retains its own license. Files are deleted by test cleanup.

`tests/test_frame_integration.py` additionally generates 7-frame MPEG-4/MOV blue video at 25 fps,
with frame selection for irregular timestamps, a two-second PTS offset, and optional B-frames.
The schedules are compared to decoded PTS and the final end. No third-party footage is involved.
Rotation, negative starts, unknown values and multiple-stream metadata are also exercised with
constructed FFprobe JSON in `tests/test_probe.py`.

`tests/test_preview_integration.py` generates eight 64×48 grayscale frames with visible seven-segment
frame numbers and distinct background levels. A stdlib `wave`/`array` recipe generates 48 kHz mono
PCM with an impulse 100 samples into each 25 fps frame. FFV1/Matroska sources are rendered into MOV
previews; decoded picture levels and impulse locations are compared across reordered cuts and
delayed audio. Other synthetic cases cover fractional FPS, VFR, start offsets and 44.1 kHz AAC.
All data is generated in test temporary directories from project code, with no third-party media.
This is the initial content/clock fixture set; the broader reusable TB-105 matrix is pending.
