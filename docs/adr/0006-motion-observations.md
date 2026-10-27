# ADR 0006 — Bounded background translation with evidence and unknown intervals

Status: accepted initial implementation (TB-202).

## Decision

Use a small deterministic integer block matcher as the first motion backend, sharing the verified
grayscale spool and source preparation with focus/exposure observations. Keep the core dependency
free. A fixed distributed patch grid, texture/ambiguity/photometric checks, exact forward/backward
consistency and spatial consensus constrain when a translation can be observed. Save accepted local
vectors, rejected-track counts, model inliers and residuals. Recompute summaries during cache loading.

An explicit user-selected background region provides attribution intent. Without one, the artifact
only reports dominant image translation, not established camera motion. Accumulate candidate paths
within contiguous accepted runs and compute time-linear middle-sample residuals from exact PTS.
Never bridge an unknown pair, label intentional pans as defects, or infer waiting from stillness.

## Consequences

This is a bounded translation baseline for short clips, not general optical flow, scene segmentation,
stabilization or a shake classifier. Rotation, zoom, parallax, subpixel motion and lighting changes
can fail its assumptions. A moving foreground that dominates the grid can dominate the model;
explicit background regions and diagnostics make that limitation visible but do not solve automatic
segmentation. Noise textures establish geometric regressions, not real-camera accuracy.

The backend uses fixed small patches and a strict pair budget to limit Python work. Extend with an
optional optimized/affine backend only after labeled footage shows the need; give that method its own
recipe and measured compatibility/performance evidence. Shared preparation/decoding changes preserve
`focus-exposure/1` formulas, settings, keys and output semantics; old quality caches remain reusable.
