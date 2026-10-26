# Manual plans and preview rendering (TB-104)

```bash
takebraid ingest ./raw/clip.mov --project ./workspace/demo
takebraid plan ./workspace/demo/assets/sha256-<digest>/asset.json \
  --stream 0 --cut 0:5 --cut 10:15 --fps 25 --audio mute
takebraid render ./workspace/demo/plans/<id>/timeline.json --project ./workspace/demo
```

`--cut FIRST:END` uses zero-based **decoded source frame indices**, with END exclusive. The saved
plan stores exact signed source PTS/time bases resolved from a ready frame map. END may equal the
source frame count. Multiple cuts can be reordered/repeated intentionally; output clips are contiguous.
No seek by rounded seconds, packet/keyframe cutting or FPS-based source index reconstruction occurs.

Audio intent is mandatory: `--audio mute`, or `--audio source --audio-stream 1` with an existing
absolute source audio stream index. Missing audio is never silently substituted for a requested track.
Use a project-registered asset; for legacy metadata run `project add` first.

## Persisted contract and execution boundary

Each `plan` call creates a new `plans/<uuid>/timeline.json` with schema v0.1, a normalized
`ManualTimeline`, project-relative asset/frame-map paths and a frame-map digest. Source metadata,
prior plans and media are never overwritten. To revise manually, create a new plan or copy/edit a
timeline within the project. There are no executable commands/filter strings in the document.

Loading reconstructs source ranges, output clocks and audio policy, then compiles against the
referenced ready map. Rendering additionally verifies project membership, full source fingerprint,
active checked scan evidence, current stream availability and plan stability. A saved flag cannot
authorize invalid cuts. A source or plan change during execution prevents completion certification.

Output FPS is an exact rational between 1 and 120, with numerator <=65535 for the native MPEG-4
encoder. Examples: `25`, `30`, `30000/1001`, `60000/1001`. Plans contain 1–64 cuts, and compiled output
is limited to one million frames. A cut that quantizes to zero output frames is rejected.

## Rounding and sampling policy

For each cumulative selected source duration T, the output endpoint is nearest(T × FPS), exact
halves upward. A clip receives the difference between adjacent cumulative endpoints. This bounds
total duration error to half an output frame, avoiding per-cut rounding drift; individual cut
durations can differ from their exact source duration by up to one output frame.

Audio endpoints are nearest(output frame endpoint × 48000 / FPS). Adjacent differences give each
clip's sample allocation, so final audio/video duration differs by at most half a 48 kHz sample.
These are quantization bounds, not claims about arbitrary source microphone/camera synchronization.

Video trim uses verified decoded frame indices. FPS conversion samples the active source picture
at output grid points (`round=up` input-boundary quantization), repeating/dropping frames as required.
The last selected picture may be held to fill the allocated output frames; no following source
picture is read into the cut. Output PTS is reset to a contiguous rational frame grid.

Source audio is resampled to 48 kHz stereo. Source PTS is retained during input decoding; absolute
cut endpoints are rounded upward to sample boundaries. Timestamp offsets/leading gaps are retained
with silence padding, and each clip is padded/truncated to its shared output allocation. No speed
change, speech alignment or music beat editing is applied. Audio discontinuity compensation follows
FFmpeg's resampler behavior and is not a general recorder-drift repair system.

## Preview format and validation

The first preview is `preview.mov`: native MPEG-4 Part 2 video (`q=3`, yuv420p), with PCM s16le audio
when selected. PCM avoids an added lossy encoder's priming/padding ambiguity during initial
sample-count verification. This is a review artifact, not a final delivery/master codec or a promise
of browser playback everywhere. MP4/AAC delivery presets and lossless mastering are future work.

The displayed image fits a 640×360 box, even dimensions, without enlarging ordinary square-pixel
inputs. FFmpeg applies input display rotation; scale corrects sample aspect ratio and sets square
output pixels. Previewing declared HDR transfer functions is rejected until a tone-mapping policy
exists. Supported initial container families are MOV/MP4, Matroska/WebM, AVI, MPEG-TS and NUT;
playlist/image-sequence inputs are outside this renderer. Media tools are not a security sandbox.

Each cut is rendered into its own generated MOV, then joined and normalized to the global output
clocks. This avoids retaining a whole source in a split graph when cuts are reordered. It re-decodes
the source per cut and re-encodes the joined preview, accepting extra I/O and generation loss for
a small, inspectable first implementation. Intermediates are preserved in the attempt directory.

Verification decodes the produced movie and checks stream layout, geometry/rotation, exact video
frame count, every video PTS and final end, plus contiguous PCM PTS and exact total audio samples.
`verification.json` records these measurements. This is counts/clocks validation, not automatic
semantic/pixel equivalence proof for all footage; indexed-picture/impulse fixtures test that behavior.

## Stages, failures and limits

Rendering uses the existing preserved-attempt mechanism. Keys include plan digest, source identity,
recipe/Takebraid/FFmpeg/FFprobe versions and timeout. A cache hit rechecks the output digest and
decodes its clocks again. `render --force` keeps prior outputs and produces a new attempt.
`timeline.json` (compiled snapshot), per-cut MOVs, concat recipe, preview, verification and terminal
receipt remain together. Only verified output publishes a completed cache pointer.

FFmpeg is launched with argument lists, `-nostdin`, `-n` and file-only protocols. Output paths are
generated inside a fresh attempt; there is no arbitrary overwrite destination. Failure/Ctrl-C after
attempt creation leaves failed/cancelled receipts and no incomplete cache hit; the CLI returns 1/130.
An old successful cache remains available after a failed forced attempt.

`--timeout` (default 300 seconds) bounds the combined FFmpeg encoding subprocess time. Preflight
hash/scan/probe work and decoded verification have separate existing timeouts (probe 30 seconds,
frame/audio scan up to 300 seconds each). It is not a wall-clock deadline for the entire command.
Temporary/intermediate disk and full-map memory scale with selected/source duration. No cleanup
or garbage collection is automatic. Multi-source timelines, transitions, overlays, OTIO export,
HDR tone mapping and automatic scene selection remain outside this slice.
