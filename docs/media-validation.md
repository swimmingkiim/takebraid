# Synthetic media validation (TB-105)

This repository includes a reproducible source generator and a separately committed expected-result
manifest, `tools/media_validation/cases.json`. These establish timing/content regression evidence for
manual previews. They do not measure camera compatibility, focus detection or editorial quality.
The tool runs from a checkout and is intentionally outside the installed product CLI/wheel.

## Reproduce

Follow the development install in the README, install FFmpeg/ffprobe, then run from the repo root:

```bash
python -m tools.media_validation --output workspace/media-validation
```

The imported Takebraid package must be this checkout (`pip install -e ".[dev]"` or `PYTHONPATH=src`).
Each run creates a new UUID directory; existing runs and sources are preserved. Nothing is downloaded.
To debug one case use `--case negative-start`; multiple `--case` flags select a subset. A subset can
pass its checks but cannot satisfy the full matrix gate. Exit code 1 means at least one case failed;
setup errors also exit nonzero. The gate additionally requires a clean Git worktree at start/end.

Keep the output directory outside Git or under ignored `workspace/`. Each case contains generated
raw signals/media, its project/timeline/render, expected.json, result.json and argument-list logs.
The top-level report.json records manifest SHA-256, generator recipe, source hashes, exact rational
source timestamps, expected/measured outputs, full FFmpeg/ffprobe version/configuration, Python,
platform/architecture, start time, Git commit and dirty flags. No absolute source paths are included
in that report; the local generator command logs do include temporary paths. Never execute these
logs as shell commands. Changes to the generator/oracle require review and a recipe bump.

## Committed oracle and cases

Expectations are committed data, never populated from the render result or timeline compiler.
The generator uses eight 64×48 pictures with homemade seven-segment digits and distinct background
levels. Audio is 48 kHz PCM with a one-sample impulse 100 samples into each source-frame interval.
Source generation uses FFV1/Matroska or MPEG-4 Part 2/MOV and no external footage, music or fonts.
All recipes/patterns are original project code under Apache-2.0; FFmpeg retains its own license.
Generated encoded bytes can differ by FFmpeg build, so compare semantic results and record hashes
rather than requiring identical container bytes. See `tests/fixtures/README.md`.

| Case | Required observation |
|---|---|
| cfr-reorder | Cuts 3:5, 0:2, 5:6 produce pictures 3,4,0,1,5 and five impulses |
| vfr-hold | Irregular source PTS produce pictures 0,0,2,3,3 at 25 fps |
| negative-start | Actually encoded negative PTS −2/25, −1/25 survive decoding; correct trims/audio |
| positive-start | Two-second source origin does not introduce output delay |
| ntsc | 30000/1001 fps yields eight pictures and 12,813 PCM samples |
| rotation-90 | Encoded display matrix is present; output geometry becomes 48×64 |
| sar-2 | Encoded 2:1 sample aspect ratio becomes square-pixel 128×48 output |
| no-audio | Silent source with explicit mute creates a video-only output |
| delayed-audio | Two source-frame delay remains silent until sample 3,940 |
| short-audio | Three-frame audio tail is padded to eight video frames |
| b-frames | Source actually contains B-frames; decoded picture order remains correct |
| repeat-64 | 64 one-frame cuts at fractional output FPS yield 77 frames, 123,323 samples, 64 impulses |
| missing-audio-rejected | Source-audio policy without audio fails with the specific validation error |

Negative PTS uses Matroska/FFV1: MOV/AVI test generation normalized the origin on the local build.
The test fails if the generator loses a requested property; metadata constructed by a unit test is
not accepted as evidence that a real encoded source had that property.

Output clocks are checked twice: production decoded verification and independent FFprobe comparison
to manifest frame count/FPS, including every PTS and the final frame's end. Decoded picture backgrounds
check identity/order on every output frame; PCM decoding checks all impulse locations and total
sample count. Rotation checks display matrix and geometry, not a general image-orientation metric.

## Tolerances declared before execution

- Source/output PTS, final ends, frame counts, dimensions and PCM sample counts: exact equality.
- PCM impulse positions: zero samples; threshold absolute amplitude >5,000 for these PCM signals.
- Grayscale background identity: absolute error ≤5 on an 8-bit sample (lossy preview encoding).
- Duration follows the documented cumulative nearest-half-up video clock. Source duration and
  quantized output duration need not be equal; audio uses that same output clock. This is not an
  AAC encoder-delay guarantee. The supported preview preset is MPEG-4 + PCM MOV.

## Evidence and supported scope

The local macOS arm64 full report is published in `docs/validation/macos-arm64.json` from a clean
run of commit `46ef0f9` (Python 3.14.4, FFmpeg/ffprobe 8.1; 13/13 passed). CI runs the full matrix on Ubuntu 24.04/Python 3.11, alongside integration tests, and publishes
JSON evidence/argument logs plus JUnit under the `media-validation-ubuntu-24.04` artifact (30 days).
Use the report's exact Git commit, manifest digest and tool versions when comparing results.
A passing run applies to that tool build and these synthetic cases; it is not a minimum-version
promise. Windows/macOS unit CI does not constitute FFmpeg media coverage on those platforms.

M1 acceptance is limited to this synthetic manual-preview slice: known CFR/VFR source boundaries,
signed/nonzero starts, display geometry, explicit audio and cumulative clocks. Real camera files,
HDR, arbitrary codecs, long recordings, multi-source composition and automatic selection need their
own evidence. M2 begins with versioned focus/exposure observations tied to exact source PTS;
measurements must remain separate from exclusion policy, and originals stay intact.
