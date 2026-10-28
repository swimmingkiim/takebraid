# ADR 0010 — Honest single-review sample labels without weakening human validation

Status: accepted pilot support.

## Decision

Add camera/assistant_review with exactly one declared AI reviewer and allow a single constructed
oracle. Camera/human validation continues to require at least two raters. Separate cohorts by media
kind, review method and defect; single-review camera reports have an explicit scope. Bump the
semantic evaluation recipe to quality-evaluation/2 and leave previous v1 evidence unchanged.

Build a small CC0 camera-derived sample package with full-frame contact sheets, rational source
labels, fixed source hashes and controlled blur/darkness intervals. Freeze calibration from one
source group before measuring other groups; keep natural haze unknown rather than treating it as
confirmed defocus. Verify decoded frame equality when rebuilding the reviewed samples.

## Consequences

A useful labeled pilot can be produced without inventing independent people or consensus. Actual
human accuracy/release validation remains incomplete. Camera-derived originals with normal/unknown
labels cannot establish recall of natural optical failures; controlled positives remain synthetic.
The explicit download/preparation tool is separate from the offline core and default tests. Sample
media remains outside Git; recipe, labels, source attribution and summarized results are reviewable.
