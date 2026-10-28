# ADR 0009 — Exact-duration evaluation with separate synthetic and camera evidence

Status: accepted harness implementation (TB-205a); camera validation (TB-205b) pending data.

## Decision

Evaluate pinned candidate-core policies against complete source-frame labels using exact durations.
Require rights/provenance declarations, explicit media kind, independent-vote structure, label version
and project/shoot splits. Preserve label disagreement and prediction abstention as distinct unknowns.
Report unconditional labeled-defect recall alongside observed-only recall so abstention cannot hide
missed defect time. Keep user-decision exclusion accounting separate from review-candidate detection.

Reuse the validated observation/interpretation/decision pipeline and preserved attempts. Recompute
scores on reuse; pin manifest bytes, policy/evidence hashes, tools and environment. Separate camera
and synthetic cohorts and retain project/scene results. Do not infer release success from CLI success.

## Consequences

The default install stays dependency-free. Initial metrics are duration-micro accounting, not event
IoU, editor-effort measurement or a calibrated automatic-exclusion guarantee. Declarations cannot
prove authorship, blind annotation or the absence of near-duplicate leakage. Public MOS datasets
need additional temporal labels for this task. Synthetic negative controls are useful precisely
because current feature policies can flag intentional low texture/darkness as defects.

No camera accuracy result is fabricated to close the milestone. M2 remains open until permitted,
labeled held-out camera footage and predeclared acceptance targets yield actual reported evidence.
