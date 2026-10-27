# Focus/exposure observations (TB-201)

`takebraid quality` measures a registered local video without selecting or excluding footage.
It saves an inspectable `quality.json` in a preserved stage attempt. The original remains unchanged.
There is no model, network access or added runtime Python dependency.

```bash
takebraid ingest ./raw/clip.mov --project ./workspace/demo
takebraid quality <asset.json> --stream 0 --size 160 --every 5
takebraid quality <asset.json> --stream 0 --size 160 --roi 10:10:80:60 --every 5
```

Stream is an absolute video stream index. `--size` is the maximum analysis edge (16..512, default
160); aspect ratio in coded pixels is preserved using integer-floor dimensions and no upscaling.
`--every N` measures decoded source frame indices 0,N,2N,… (default 1). VFR sample times are uneven:
source PTS/time base are saved exactly; average FPS is never used to infer positions. Unsampled
frames have no measurement and must not inherit a neighboring sample's quality interpretation.

ROI is X:Y:WIDTH:HEIGHT on the resized, unrotated coded pixel grid. It must fit and be at least 3×3.
Omit it for the entire analysis image. Coordinates do not follow objects; non-square source pixels
are not normalized to display aspect ratio. Use the saved geometry/settings when comparing results.
Very small ROIs have few derivative samples and are not reliable focus evidence.

## Defined features, recipe `focus-exposure/1`

FFmpeg applies area resizing and converts to 8-bit `gray`. Color range/matrix conversion follows the
recorded FFmpeg build and source metadata. These are encoded grayscale statistics, not linear-light
photometry. Missing color tags are recorded as unknown metadata, not guessed or certified as SDR.
For each selected frame and ROI:

- `mean_luma`: arithmetic mean of all ROI code values divided by 255.
- `luma_variance`: population variance of ROI values divided by 255².
- `dark_fraction`: fraction of ROI pixels with code value ≤16.
- `bright_fraction`: fraction with code value ≥235.
- `laplacian_variance`: population variance of L=left+right+up+down−4×center over the ROI interior,
  divided by 255²; border pixels supply neighbors but are not derivative centers.

JSON values are numerator/denominator pairs. The definitions and cutoffs are fixed in the recipe,
not tunable defect thresholds. Bright/dark fractions describe these codes; they do not establish
sensor clipping or bad exposure. Laplacian variance is texture/noise/scale dependent, not a calibrated
focus score. A smooth product or dark intentional scene can have low values and remain usable.
No cross-camera ranking, probability, good/bad label or automatic discard is implemented.

## Coordinates, persistence and limits

Each row contains decoded `frame_index`, signed integer source `pts`, and the five metrics. Inputs
record source SHA-256/asset/stream, exact time base, frame-map digest, recipe/version, complete
FFmpeg/ffprobe version/configuration, color metadata, geometry, settings and timeout. Same-pass
source PTS, progressive scan and dimensions are checked against the map before publishing. The
[FFmpeg showinfo documentation](https://ffmpeg.org/ffmpeg-filters.html#showinfo) defines its timestamp
fields; the adapter compares integer PTS through exact rational clocks.

Repeated calls rehash the source and validate cache receipt/checksum, schedule, identity, geometry,
metric fields and rational bounds. `--force` saves another attempt. Changed method/settings/map/tool
builds use separate stage keys. Failure/cancellation preserves a terminal receipt, not a completed
cache result. A source/map change during analysis prevents certification.

Supported initial inputs: ready decoded maps; video in MOV/Matroska/AVI/MPEG-TS/NUT families; listed
8-bit gray/YUV planar/RGB(A) formats; no declared display transform or HDR/wide-gamut metadata.
Other declared formats, transforms, untrusted timing or budget overflow produce `status: unknown`,
reason codes and an empty observation array (CLI exit 2). Unknown does not mean usable footage.
Invalid arguments, missing tools, decode errors, interlaced/dynamic geometry discovered during decode,
or mismatching clocks fail (exit 1); interruption exits 130. Successful observations exit 0.
Undeclared HDR cannot be detected by these code-value measurements.

The decoder has a 256 MiB predicted raw spool budget (plus at most one guard frame), 10,000 measured
samples and the scan's 250,000-frame limit. Reduce `--size`, increase `--every` for sample overflow,
or use shorter sources. Sparse sampling reduces measurement CPU/output size but still decodes all
frames. `--timeout` bounds each scan/decode subprocess, not total wall-clock orchestration; metadata
and tool probes have separate short timeouts. Temporary raw pixels/logs are removed after processing.
This first slice is intended for short clips; no performance claim for long camera originals.

## Evidence and next boundary

Unit fixtures have hand-calculated impulse and uniform-image statistics. Actual FFV1 grayscale
sources contain a checker pattern, a generated box-blurred version, black, white and middle gray;
tests require lower high-frequency variance after blur and exact brightness fractions. Reusable
TB-105 sources verify negative/nonzero PTS, VFR, NTSC, ROI/sampling and bounded resizing. Fake-tool
tests cover cache corruption, source mutation, unsupported HDR and failure/cancellation receipts.
All patterns/blur recipes are original Apache-2.0 project code with no third-party media or fonts.
Local FFmpeg 8.1 and Ubuntu CI FFmpeg are exercised by the integration suite; report CI evidence
with the specific PR/run before asserting compatibility with another build.

TB-202 adds background-motion observations. Defect interpretation, temporal policies, reversible
exclusions and real-footage precision/recall remain TB-203..205. Measurements can inform later
review, but this command never edits a timeline or deletes source material.
