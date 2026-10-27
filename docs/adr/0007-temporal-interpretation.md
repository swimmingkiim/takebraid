# ADR 0007 — Explicit temporal policies produce review candidates

Status: accepted initial implementation (TB-203).

## Decision

Require an explicit versioned policy containing metric, calibration context, enter/exit thresholds,
minimum duration and padding. No default detector thresholds or quality probability are supplied.
Interpret only completed, checksummed, domain-validated observations with verified source/map/tool
identity. A preserved older observation remains usable after a force run advances its cache pointer.

Quality measurements occupy only their decoded frame's presentation cell. A background-path residual
occupies only the middle sampled frame's cell, and requires a declared background region. All other
cells remain unknown; no interpolation or sample hold fills sparse coverage. Unknown cells reset
hysteresis and split minimum-duration evidence. Minimum duration uses exact source time before padding.
Padding snaps outward to decoded boundaries within the same contiguous measured component.

Keep candidate cores, padded review ranges, evidence indices, per-cell threshold states and rejected
short runs. Overlapping padded proposals do not merge distinct cores. Outputs explicitly declare
`artifact_kind: interpretation` and `decision_effect: none`; reversible decisions follow in TB-204.
Cache reuse recomputes the complete result from observations/policy instead of trusting saved flags.

## Consequences

The user must supply a calibration-scoped policy; arbitrary thresholds can still make poor candidates.
The supplied example is synthetic, not a camera calibration. Low detail, darkness, bright codes and
path variation can be intentional. Full unknown coverage is safer than inventing measurements, and
sparse sampling often prevents minimum-duration confirmation. Motion endpoints/residual gaps remain
unknown even for a successful translation run. This slice establishes temporal arithmetic and evidence
traceability, not defect precision/recall or unattended editing quality.
