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


`tests/test_quality_integration.py` generates original checker and 5×5 box-blur patterns plus
black/white/mid-gray frames as FFV1/Matroska. The Apache-2.0 stdlib recipe has no external image
assets. Hand-calculated point-impulse/constant metrics live in `test_quality.py`; TB-105 sources
also exercise quality sampling on signed, offset, VFR and fractional clocks. These establish
measurement behavior, not camera-focus or exposure classification accuracy.


`tools/motion_fixtures.py` generates seeded grayscale textures with known integer translations,
independently moving patches, a declared background region, flat/periodic signals and occlusion.
`tests/test_motion_integration.py` encodes FFV1/Matroska and MPEG-4/MOV cases with signed/nonzero,
VFR and NTSC clocks; committed test expectations specify displacements and unknown outcomes.
These Apache-2.0 project recipes contain no third-party media. They validate the bounded translation
method and exact path arithmetic, not camera/subject segmentation or shake classification accuracy.


TB-203 fixtures in `tests/test_interpretation*.py` use hand-calculated source-time cells, generated
bright/mid-gray FFV1 signals and original TB-202 jitter textures. MPEG-4/MOV checks VFR and NTSC
final presentation ends. The synthetic example policy is not camera calibrated. These Apache-2.0
project recipes test temporal logic and preserved evidence; no external footage/dataset is used.


TB-204 reuses the original visible-index/PCM fixtures to verify explicit exclusion and restoration
through actual decoded previews. Pure source partitions cover baseline review/unknown and ordered
overrides; integration checks picture order, PCM impulse positions, snapshot/parent provenance and
render dependency mutation. No new third-party footage or licensing dependency is introduced.


TB-205a uses hand-calculated duration tables and generated FFV1 signals with independent constructed
scoring labels, including deliberate label disagreement and intentional-scene false positives.
`tools/evaluation_fixture.py` reproduces static-product, intentional-dark, box-blur and pan controls.
Oracle IDs are constructed votes, not human annotators. All recipes/labels are original Apache-2.0
project material; no external camera dataset or model pseudo-label is distributed.


The licensed pilot in `examples/labeled-pilot/` records CC0 camera source hashes and one AI review,
with constructed blur/darkness variants kept separate. Runtime videos/contact sheets are generated
under ignored workspace data, not committed. Metadata-contract tests use generated signals and do
not count as real camera evidence. Human review still requires two raters; assistant review uses one.
