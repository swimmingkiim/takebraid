# ADR 0011 — Local prediction-hidden review packets, with explicit attestations

Status: accepted tooling slice; human study and browser visual QA remain pending.

## Decision

Keep annotation preparation in checkout tools, separate from quality measurement and evaluation.
Export bounded decoded PNG frames and exact PTS metadata into a standalone offline HTML packet;
retain original-manifest/task binding privately outside the reviewer directory. Do not expose prior
labels, predictions or calibration/test identities. Support explicit unknown and full source-frame
coverage, independent human attestations and immutable JSON exports.

Collect at least two distinct declared humans into a new evaluation manifest. Reverify media,
clock, images and frozen manifest; retain every vote and represent disagreements through existing
unknown-consensus duration scoring. Keep constructed labels/policies/splits unchanged. This does
not change evaluation recipe semantics, create editing decisions or authorize automatic exclusion.

## Consequences

Human review can proceed on a concrete handoff without a backend, cloud account or browser codec
support for FFV1. PNG review is larger and loses live playback; downscaling limits optical judgment.
The existing trusted-clock/analysis limitations bound the first implementation. Hardware/tool
revisions are recorded; different tool builds need a new preparation/validation run.

A checkbox cannot establish identity, independence or study quality. No artificial extra raters or
completion claims are generated. Prior unblinded reviewers cannot validate the same pilot blindly.
The initial sample still lacks natural positives and more scene genres. Publishing or sending a
packet remains a separate action governed by source rights. Actual local-browser QA must be reported
separately from synthetic handler tests.
