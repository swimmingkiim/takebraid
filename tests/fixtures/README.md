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
The shared indexed signal generator lives in `tools/media_validation/fixtures.py`.

TB-105 adds `tools/media_validation/cases.json`: an independent committed oracle for 13 generated
scenarios, including actually encoded negative PTS, rotation/SAR, B-frames and repeated-cut rounding.
Run `python -m tools.media_validation --output workspace/media-validation` from a development checkout.
Sources and previews remain in that ignored output directory for inspection/reuse; JSON reports bind
observations to source hashes, manifest digest, tool builds and code revision. No third-party datasets
or checkpoints are used. The original patterns, recipes and manifest are Apache-2.0 project material.
See `docs/media-validation.md` for the case matrix, tolerances and evidence scope.
