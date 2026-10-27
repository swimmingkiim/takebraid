# Background translation observations (TB-202)

`takebraid motion` saves motion candidates and tracking diagnostics without changing originals or
timelines. It requires FFmpeg/ffprobe but adds no Python dependency, model download or network use.

```bash
takebraid motion <asset.json> --stream 0 --size 96 --every 1 --radius 4
takebraid motion <asset.json> --stream 0 --background 64:0:32:64
```

The stream is an absolute video stream index. `--size` is the maximum analysis edge, 32..192 (default
96), with no upscaling and integer-floor aspect-preserving coded dimensions. `--every` samples frame
indices 0,N,2N,…; each consecutive sampled pair has its actual signed source PTS/time base. Increasing
it increases displacement per pair and can exceed the search radius. Unsampled activity is not
measured. A final frame outside this stride is not appended or extrapolated.

`--background X:Y:WIDTH:HEIGHT` restricts patches and search candidates to a fixed user-declared
background rectangle on the resized, unrotated coded pixel grid. It does not track a subject. Both
region dimensions must be at least 2×radius+10 and fit the grid. The default whole-image model is
`dominant_image_translation`; with a region it is `declared_background_translation`. Neither label
proves camera motion: a foreground object can dominate the image, and a declared region can be wrong.
No automatic foreground/background segmentation is implemented.

## Fixed method: `background-translation/1`

Area resizing and 8-bit grayscale conversion reuse the TB-201 decoder. Same-pass integer PTS,
progressive scan, frame count and source dimensions must match the validated map. See [quality
observations](quality.md) for color, geometry, container and spool limits. ROI coordinates refer to
coded pixels; non-square pixels are not normalized to display aspect ratio.

The deterministic matcher uses:

1. A 6×4 grid of patch centers in the declared region, with a radius+2 border margin.
2. A 5×5 patch; population code-value variance ≥64 is required in both images.
3. Exhaustive integer search within ±radius (2..6, default 4), using summed absolute differences.
   Best SAD must be ≤500 (mean ≤20); runner-up cost must exceed it by at least 125 (mean margin ≥5).
   A best vector touching the search radius is rejected rather than certified as a bounded estimate.
4. Reverse matching must pass those same checks and return exactly to the original center.
5. At least 12 surviving tracks. A unique most-common exact vector proposes the translation; a tie
   yields unknown. Inliers lie within squared distance ≤1 of that vector. At least eight inliers,
   at least 60% of surviving tracks and coverage of all four region quadrants are required.

These thresholds define correspondence acceptance, not defect thresholds or calibrated confidence.
The model keeps its modal integer vector; it does not fit rotation, zoom, affine or perspective motion.
The methodology treats optical flow as apparent motion, which can arise from either objects or the
camera; see the [OpenCV optical-flow introduction](https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html).
No OpenCV code or dependency is used in this implementation.

## Output and path coordinates

A preserved stage attempt contains `motion.json`. Its inputs bind source/map SHA-256, exact clock,
recipe/settings, code version, complete tool build versions/configurations, geometry and color
metadata. Every pair includes `from_frame`, `to_frame`, `from_pts`, `to_pts`, accepted track positions,
integer dx/dy/SAD, rejection counts, inlier indices and mean squared inlier residual. Positive dx/dy
means image content moved right/down in analysis pixels. Local vectors outside the inlier set remain
available as evidence of model disagreement; they are not automatically labeled subjects.

An unreliable pair has `status: unknown`, a reason, null translation/residual and no model inliers.
Rejection counts distinguish low texture, ambiguous matches, photometric mismatch, search boundary
and forward/backward failure. Consensus diagnostics distinguish too few tracks, competing modes
and insufficient spatial support. Unknown is never replaced with a zero vector.

`path` contains one row per pair. For observed pairs it accumulates displacement from zero at the
start of a contiguous accepted run, records that run's starting frame, and stores exact rational
velocity in analysis pixels/second. After an unknown pair, path coordinates restart; they do not
claim a common origin across the gap. For two adjacent observed pairs with displacements d₀,d₁ and
actual durations t₀,t₁, the residual at their shared middle sample is:

```
r = (d₀ × t₁ − d₁ × t₀) / (t₀ + t₁)
```

The row explicitly records `residual_at_frame`/`residual_at_pts`. This is the middle candidate path
point minus its time-linear interpolation between neighbors. Constant-velocity pans have zero
residual even at unequal VFR intervals. A nonzero residual describes local path variation; it does
not establish unwanted shake. Paths can drift, integer quantization matters, and the baseline cannot
distinguish every deliberate movement, moving foreground, rolling shutter or scene cut.

## Persistence, unknowns and limits

Cache loading checks receipt/checksum and source identity, then reconstructs schedules, validates
track coordinates/costs/rejection accounting, and recomputes consensus, status and the complete path.
It does not trust saved summary flags. `--force` preserves a new attempt. Source/map mutation blocks
certification; failure/cancellation receipts retain the attempted run. Source/timeline data is never
edited. Shared extraction leaves prior `focus-exposure/1` cache identities and measurements unchanged.

Whole-run status is `observed` when every pair has a supported model, `partial` when only some do,
and `unknown` when none do or preflight rejects the source. The CLI exits 0/2/2 respectively; inspect
pair coverage before using any result. Invalid arguments, tool/decode/clock failures exit 1;
interruption exits 130. Unsupported declared HDR/display transforms/pixel formats, untrusted maps,
small analysis regions, fewer than two sampled frames or budget overflow produce unknown artifacts.

Limits: 500 sampled pairs, predicted 256 MiB decoded spool plus one guard frame, source scan limit
250,000 frames. Sparse sampling still decodes every source frame. Each scan/decode subprocess uses
`--timeout` (default 300 seconds); it is not a global CPU deadline. The fixed grid, patch, radius and
pair limits bound matcher work. This Python baseline targets short clips, not real-time analysis.

## Synthetic evidence and remaining validation

Original project recipes in `tools/motion_fixtures.py` generate translated seeded textures and
independently moving patches. The expected translations are committed test data, not learned from
the estimator. Encoded FFV1/Matroska fixtures verify these exact analysis-pixel expectations:

| Fixture | Expected pair translations / outcome |
|---|---|
| Static textured image | 0,0,0 horizontally; observed, not a waiting/exclusion label |
| Constant pan | +1,+1,+1; zero path residual |
| Alternating path | +2,−2,+2; middle residual +2 then −2 |
| Small independent subject | Static background model despite local moving correspondences |
| Pan plus independent subject | +1 background candidate with local disagreement |
| Majority foreground, declared right-side background | 0 for the selected background |
| Flat / periodic / full occlusion / search-boundary translation | Unknown, null model/path |

Tests also require unknown when only a localized subject has texture; exact negative/nonzero PTS,
MOV VFR and 30000/1001 clocks; path reset at unknowns; cache/settings/force behavior, record tampering,
source mutation and failure/cancellation. Integer synthetic translations and path rationals use exact
expectations; this is not a subpixel-error or real-footage accuracy benchmark. Generated patterns
and recipes are Apache-2.0 project material; no camera footage, people, external fonts or datasets.

Real cameras, rotations, zoom, depth/parallax, low light, heavy compression and calibrated shake
precision/recall need held-out footage in TB-205. Temporal defect interpretation follows in TB-203;
reversible keep/exclude policy is TB-204. This command does not discard footage or stabilize pixels.
