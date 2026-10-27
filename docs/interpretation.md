# Temporal review candidates (TB-203)

`takebraid interpret` applies an explicit policy to saved quality or motion observations. It writes
an interpretation, never a keep/exclude decision, modified source or timeline. No model or new Python
dependency is required. Existing metadata/frame-map/tool verification still requires FFmpeg/ffprobe.

```bash
takebraid quality <asset.json> --stream 0
# Use the printed quality.json path; choose a policy calibrated for your observations.
takebraid interpret <quality.json> --asset <asset.json> --policy ./policy.json
```

The repository example `examples/policies/synthetic-bright.json` exists for generated fixtures only:

```json
{
  "schema_version": "0.1",
  "name": "synthetic-bright",
  "calibration": "Synthetic 8-bit FFV1 gray full-frame fixture only; not camera calibrated.",
  "metric": "bright_fraction",
  "enter": "9/10",
  "exit": "4/5",
  "minimum_seconds": "2/25",
  "pad_before_seconds": "1/50",
  "pad_after_seconds": "1/50"
}
```

All fields are required; additional fields are rejected. Numeric values are nonnegative integer,
decimal or fraction strings, with bounded digits/denominators and no exponent/nonfinite notation.
`name` is a short lowercase identifier; `calibration` must describe the intended evidence context.
That text is recorded, not independently certified. Choose thresholds for the actual analysis scale,
ROI, source class and metric units. There are no default operational thresholds.

## Supported evidence

| Policy metric | Observation recipe | Entry/exit direction and units |
|---|---|---|
| laplacian_variance | focus-exposure/1 | Enter ≤ threshold; exit ≥ threshold; normalized variance |
| dark_fraction | focus-exposure/1 | Enter ≥ threshold; exit ≤ threshold; fraction [0,1] |
| bright_fraction | focus-exposure/1 | Enter ≥ threshold; exit ≤ threshold; fraction [0,1] |
| path_residual_squared | background-translation/1 | Enter ≥ threshold; exit ≤ threshold; analysis pixels² |

Low-direction entry must be strictly below exit; high-direction entry must be strictly above exit.
Equality at the entry/exit boundary triggers the corresponding transition. Minimum duration is
positive and at most 3,600 seconds; each padding value is at most 60 seconds. Laplacian thresholds
must lie in [0,16], fractional thresholds in [0,1]. These are mathematical validation bounds, not
recommended defect thresholds. Path variation is neither camera-shake probability nor motion speed.

Quality evidence is assigned to exactly `[frame.pts, next presentation boundary)` for the measured
frame, including a verified final presentation end. A skipped frame is unknown even if adjacent
samples have the same value. Unknown/unsupported observations supply no metric values.

Motion uses squared middle-sample residual components from a **declared background** report, not a
dominant full-image model. The value is assigned only to that middle decoded frame's presentation
cell; it is not spread over the adjacent motion pairs. First/last samples and missing/unreliable
residuals remain unknown. Without an explicit background region, all motion interpretation cells
are unknown with `background_not_declared`; this does not imply usable or unusable footage.

## Temporal behavior

For each contiguous measured component, the engine begins inactive. Crossing entry starts a core;
values inside the hysteresis band retain the active state until exit. A dead-band value cannot start
a core while inactive. Exit excludes the release cell. Unknown immediately closes the current core
and resets state; no duration or hysteresis carries across it.

A core survives only when its exact `[in,out)` duration meets the policy minimum. Short runs remain
in `short_runs` with their evidence and a reason. Threshold states in `cells` describe transitions,
not final decisions: `enter`, `hold`, `no_trigger`, `unknown`. `no_trigger` does not mean good footage.

After duration filtering, padding extends the review range, snapping outward to decoded frame
boundaries. Padding is clamped to the source bounds and the same contiguous measured component;
it cannot swallow an unknown frame. Core and padded endpoints are separate fields. Evidence indices
and minimum/maximum values refer to the core only. Separate cores remain separate even when their
padded ranges overlap; this preserves the intervening release evidence for later human review.

All clocks/durations are integer PTS plus exact rational time bases. No FPS-derived position,
floating-second comparison or interpolation is used. Signed starts, unequal VFR durations and NTSC
final ends are exercised directly in tests.

## Integrity, storage and exit codes

The observation must be an original completed artifact in the asset's project, with matching terminal
receipt, stage identity, checksum and validated metric/track/path contents. Preserved older attempts
are accepted after force reruns. Copies outside the project, incomplete artifacts, tampering, a wrong
asset, or changed source/map/tool revisions fail; regenerate observations when revisions differ.
No quality/motion measurement is rerun by this command, but metadata checks and a missing frame-map
cache may require a scan. Unsupported timing produces an unknown report without fabricated bounds.

`interpretation.json` is stored in a preserved stage attempt. Inputs contain observation and policy
hashes, normalized policy, observation provenance and interpretation recipe `temporal-candidates/1`.
The artifact declares `artifact_kind: interpretation`, `decision_effect: none`, and retains the
observation's unsupported-input reasons separately from per-cell coverage reasons. Candidate fields are
`core_in_pts`, `core_out_pts`, padded `in_pts`, `out_pts`, exact `duration_seconds`, evidence indices
and metric extrema. It also retains all evidence cells and rejected short runs.

Changing policy bytes/settings or observation inputs creates a separate stage key; `--force` retains
a fresh attempt. Reuse verifies the cache receipt/checksum and recomputes the full interpretation.
Source/map/observation/policy changes during execution block certification. Failure and cancellation
preserve terminal receipts for an execution attempt. Nothing is sent over the network.

Exit 0: all source cells interpreted. Exit 2: partial or wholly unknown coverage, even if useful
candidates exist. Exit 1: invalid policy/input, integrity or tool error. Exit 130: interruption.
The output path is printed for successful publication, including exit 2. A report with no candidates
does not establish that the footage is usable.

## Evidence and next boundary

Hand-calculated fixtures check hysteresis equality/dead bands, unknown resets, exact minimum duration,
VFR/signed boundaries, outward padding and short spikes. Encoded FFV1/MOV fixtures exercise bright
runs, sparse quality, declared-background jitter, VFR and 30000/1001 final ends. Integrity tests cover
policy changes, cache reuse/force, older attempts, corruption, source/policy mutation and terminal
failure/cancellation. These synthetic fixtures establish arithmetic, not camera defect accuracy.

TB-204 adds explicit reversible keep/exclude/review/unknown decisions with restoration overrides;
TB-205 still owns held-out defect precision/recall and intentional-scene failure cases. Automatic
exclusion remains unimplemented in this slice.
