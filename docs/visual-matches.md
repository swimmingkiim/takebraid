# Spatial visual-match baseline (TB-301a)

`takebraid visual` observes and caches a small grayscale descriptor, then proposes similar sampled
frames across source assets for human inspection. This is a transparent baseline for later learned
image embeddings and duplicate-take proposals. It does not recognize actions, establish semantic
relevance, label whole takes as duplicates, select clips or change editing decisions. M2 human
quality validation remains open; this independent measurement slice does not require automatic
quality exclusions and does not claim either M2 or M3 sign-off.

## Observe and compare

```bash
takebraid visual observe /absolute/path/asset-a.json --stream 0 --size 64 --every 25
takebraid visual observe /absolute/path/asset-b.json --stream 0 --size 64 --every 25
# Use the returned visual.json paths, and set explicit uncalibrated search tolerances.
takebraid visual compare \
  --input /absolute/path/asset-a.json /absolute/path/visual-a.json \
  --input /absolute/path/asset-b.json /absolute/path/visual-b.json \
  --output workspace/visual-comparison --max-distance 1/100 --min-variance 1/10000 --limit 20
```

`--every` is a decoded-source-frame stride, not seconds or FPS. For VFR and signed source starts,
each sampled frame retains its actual source index, PTS, rational time base and stream identity.
Descriptor observations follow the existing same-pass decode/PTS verification and source/map/tool
checks. A completed receipt and checksum are required when loading descriptors for comparison.
Sources are opened read-only. Failed/cancelled attempts are preserved; `--force` writes another
attempt. Repeating with matching checked inputs reuses a completed result. A comparison may use
an older intact observation attempt; the current pointer need not name that exact attempt.

The explicit tolerances above are examples, not calibrated recommendations or accuracy guarantees.
`--max-distance` is required, in [0,1]; `--min-variance` is required, positive and at most 1/4.
There is no similarity probability or hidden defect threshold. Observation CLI returns 2 for
unsupported input with an `unknown` artifact, 1 for an error and 130 for cancellation. Comparison
success means a valid proposal report was written, including when there are no comparable samples.
Read its `input_status`, low-texture counts and incompatible-aspect counts before interpreting it.

## Method and limits

Recipe `gray-spatial-grid/1` decodes a bounded, unrotated grayscale grid (default maximum edge 64;
no upscaling). Divide it into 8x8 rectangular cells using integer boundaries. Each coordinate is the
exact cell average divided by 255. The 64 rational coordinates are spatial intensity features,
not learned or semantic embeddings. A fine checkerboard can average to a flat descriptor even
when native pixels have texture; the contrast gate concerns this descriptor's spatial variation.

Recipe `spatial-match-proposals/1` computes the mean squared difference of the 64 coordinates.
Distances include brightness differences. Texture eligibility is the population variance of cell
means. Samples below the explicit contrast floor supply insufficient evidence and are not scored.
They are not labeled defective or proven dissimilar. Coded-pixel aspect ratios must match exactly (sample aspect ratio is not normalized);
other source-pair combinations are counted separately and not scored. Scaling, color conversion,
compression, framing, cuts, overlays and subject/camera motion can all change distances. Conversely,
different scenes can have the same cell means. These are failure modes, not editorial alternatives
the system has resolved. The baseline sees no color, intent, event completeness or take boundaries.

Each match contains both source assets' exact frame positions and a rational distance. The report
returns at most `--limit` matches (default 20, maximum 1000) and reports total matches/truncation.
Ties are deterministic by distance, asset identity and frame indices; input order does not change
the report. It does not collapse adjacent pairs into duplicate windows or infer unsampled coverage.
`semantic_equivalence_validated` and `automatic_exclusion_validated` are false.

Observation supports at most 1000 sampled frames per asset, plus the existing 256 MiB decoded-spool
budget and supported-media restrictions. Comparison accepts 2..10 distinct source content IDs,
at most 2000 total samples and 50,000 possible cross-source sampled pairs before texture/aspect
filtering. Increase the observation stride or reduce the input set to stay inside the budget.
Sparse sampling reduces comparison work but still decodes every source frame for clock checks.

## Evidence

Generated broad spatial patterns give exact zero-distance matches across independently encoded
assets; reversed patterns do not pass a zero-distance threshold; uniform frames provide no contrast
evidence. Unit tests cover non-divisible cell geometry, exact threshold equality, rational bounds,
budget enforcement, aspect gating and deterministic ranking. Actual FFmpeg integration tests cover
cache/force history, receipt tampering, unsupported narrow grids, CLI execution, negative source
starts and VFR coordinates against the independent media oracle. These tests establish mechanics,
not duplicate-take accuracy or semantic relevance.

The existing nine CC0 pilot clips also have a local measurement run under `workspace/visual-pilot/`.
They contain excerpts and controlled variants, not independent duplicate-take labels. The public
[validation summary](validation/visual-baseline-summary.json) records counts,
source/descriptor/report hashes and search settings. No human
annotation is invented from the resulting matches. Learned providers, broader camera footage,
held-out duplicate-take labels and end-to-end correction measurements remain future work.
