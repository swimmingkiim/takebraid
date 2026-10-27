# ADR 0005 — Exact pixel observations before quality decisions

Status: accepted initial implementation (TB-201).

## Decision

Start with dependency-free grayscale measurements on a bounded, declared analysis grid. Compute
normalized four-neighbor Laplacian variance, mean/variance and dark/bright code-value fractions using
integer sums and exact rationals. No focus probability, defect threshold or exclusion decision is
produced. ROI coordinates belong to the unrotated analysis pixel grid, not a moving subject.

The media adapter decodes to a temporary disk spool. Same-pass FFmpeg `showinfo` source PTS are
cross-checked against the validated frame map, including signed/VFR clocks, before sampling by
frame index. Stage keys include source/map hashes, method/settings and full tool build revisions.
Existing receipts/loaders protect cache reuse, failures and cancellation. Unsupported declared input
produces an unknown observation artifact with reasons and no measurements.

## Consequences

The core package gains no CV/model dependency. Small sources can be inspected on any machine with
validated FFmpeg capability. Standard-library pixel loops trade throughput for a transparent baseline;
future optimized backends need equivalent fixtures and their own method revision. The disk/CPU work
still decodes every frame even with sparse sampling. Raw decode and sample budgets bound this first
slice; long sources need a later streaming implementation.

Measurements depend on texture, resizing, color conversion, compression and noise; a uniform image's
zero focus feature is not a focus failure. Encoded grayscale statistics are not calibrated scene
exposure or sensor clipping. M2 policy/calibration and held-out footage evaluation remain separate.
