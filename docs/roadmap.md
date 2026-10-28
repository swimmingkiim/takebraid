# Development roadmap

Status as of 2026-10-29. Milestones are dependency ordered and judged by exit evidence, not dates.
Initial scope: dialogue-free process/product footage, chronological assembly and a reviewable first cut.

## M0 — Bootstrap (implemented; initial remote CI passed)

- [x] Apache-2.0 project, bilingual README, contribution/security guidance.
- [x] Installable `src/` Python package; version and environment discovery CLI.
- [x] Exact source clock/range values and unit tests.
- [x] CI for lint, format, unit tests, build and installed-wheel smoke check.
- [x] Architecture, ADRs, contracts, research and evaluation plan.

M0 delivered infrastructure only. Metadata ingest is delivered separately in TB-101 below.

## M1 — A trustworthy media slice

Deliverable: inspect a short original, describe its frame timestamps, save a manually chosen range,
render a preview, and verify it against that range. This is the first implementation priority.

- [x] TB-101: `ingest` reads ffprobe JSON into versioned asset metadata; preserves rotation, missing
  audio, fractional frame rates and signed starts. Missing A/V time bases are rejected; frame
  continuity is explicitly unverified until TB-102. See `ingest.md`.
- [x] TB-102: decode source PTS maps, validate exact source boundaries and map proxy sample
  coordinates through explicit 1x clocks/origins. Uncertain timing is diagnosed without repair;
  proxy generation is separate. See `frame-maps.md`.
- [x] TB-103: versioned project registry, content-verified relinking, validated asset/frame-map
  loaders and content-addressed scan attempts with checked cache reuse and terminal receipts.
  Future plan records will use the same publication primitives. See `projects.md`.
- [x] TB-104: saved/validated manual single-source timelines, frame-index trims, rational output
  clocks, explicit audio policy and decoded MOV preview verification; preserved render stages,
  cancellation/failure receipts and no source/output overwrites. See `previews.md`.
- [x] TB-105: reusable synthetic source generator and independent 13-case media oracle, exact
  boundaries/PCM impulses, provenance reports and CI evidence. See `media-validation.md`.

Exit: fresh-checkout instructions work on a declared platform; CFR boundaries match intended frames;
VFR mappings match known PTS; nonzero/negative PTS and rotation survive; output duration agrees with
the timeline within the documented frame rounding policy; audio does not accumulate drift.
Record tolerances before evaluating, including codec delay and final-frame duration handling.

### Delivered slice: TB-101

Input: local media path and explicit project output directory. Output: validated `asset.json` with
schema version, asset ID/fingerprint, source locator, per-stream time base, duration/start metadata,
rotation, color and audio metadata. Source is opened read-only.

Acceptance: malformed ffprobe output, missing executable, invalid media and multiple streams produce
actionable errors; missing audio is valid; fractional FPS is preserved as a rational; no average-FPS
source-time conversion; synthetic fixtures verify the parser and one real subprocess integration.
Implement the media adapter, parser, artifact writer and `ingest` CLI as one working change.

### Delivered slice: TB-102

Build a decoded frame PTS map keyed by asset and stream index. Preserve signed PTS, variable frame
intervals and final presentation end; distinguish missing/non-monotonic timestamps from supported
input and define repair/unsupported outcomes. Do not infer frame positions from average FPS.
Verify against generated CFR/VFR/nonzero-start cases before implementing proxy mapping.
TB-101's full fingerprint and one-file publication support this slice; TB-103 still owns the project
registry, multi-artifact cache reuse and general stage persistence.

### Delivered slice: TB-103

Implement a versioned project registry and validated artifact loaders, source relinking and changed-media
checks, deterministic stage keys, and atomic completed/failed/cancelled stage receipts. Preserve
user edits and prior artifacts; never reuse partial or stale outputs. Frame-map loaders must recompute
domain validity instead of trusting a saved status. Proxy generation/rendering follows the trusted
source-map and registry foundation in TB-104.

### Delivered slice: TB-104

Persist and validate a manual single-source timeline using a ready decoded map. Render selected
half-open frame ranges into a low-resolution preview with an explicit output clock/audio policy.
Protect sources and existing renders, record stage receipts and validate actual duration/frames
and audio alignment. Use synthetic frame indices/audio impulses to establish rounding tolerances.
Do not infer cut positions from FPS or execute unvalidated saved timeline fields.

### Delivered slice: TB-105

Expand the initial visible-index/impulse fixtures into a reusable, documented validation suite with
expected source/output manifests: negative/nonzero starts, VFR, fractional FPS, rotation/SAR,
missing/delayed/short audio, B-frame codecs and long repeated-cut rounding. Record supported tool
versions/platforms and regression tolerances, including content checks beyond counts/clocks. M1
sign-off uses the clean full report and Ubuntu CI evidence described in `media-validation.md`.
This closes only the synthetic manual-preview slice, not real-camera or editorial-quality validation.

### Delivered slice: TB-201

Implement versioned focus/exposure observations on decoded source frames, with explicit sampling
coordinates, analysis scale and optional ROI. Keep measurements separate from defect labels and
exclusion policy. Save method/settings/tool provenance in checked stage keys. Establish synthetic
sharp/blurred and brightness/clipping fixtures; report unknown for unsupported input rather than
claiming a quality verdict. No automatic discard or model download in this slice.

### Delivered slice: TB-202

Add background-motion estimation with explicit sampling/scale and tracking diagnostics. Distinguish
subject motion from camera motion where the evidence permits; unreliable/insufficient tracks must
yield unknown. Preserve measurement/policy separation and source-clock provenance.

### Delivered slice: TB-203

Introduce explicit, versioned interpretation policies for measured defect candidates, temporal
hysteresis, minimum duration and boundary padding. Preserve unknown/unsampled coverage and source
clocks; do not turn low texture, darkness or movement alone into automatic exclusions. Require
synthetic temporal boundary evidence before reversible decision records in TB-204.

### Delivered slice: TB-204

Persist explicit keep/exclude/review/unknown decision intervals and restoration overrides, preserving
interpretation provenance and exact source coverage. Apply validated user decisions to a manual
preview without source modification; never silently promote review candidates to automatic exclusion.

### Current task: TB-205

Build a reproducible evaluation harness and rights/provenance inventory for labeled defect/normal
footage, split by shoot/project. Measure per-defect precision/recall, intentional-scene false positives
and excluded normal time. Publish unsupported cases and only claim accuracy supported by actual
licensed held-out annotations; synthetic regressions remain separate from camera/editorial evidence.

## M2 — Quality analysis and reversible decisions

- [x] TB-201: exact source-PTS focus/exposure observations, bounded analysis scale/ROI, checked
  cache and synthetic blur/brightness evidence. See `quality.md`; no exclusion verdicts.
- [x] TB-202: bounded background translation candidates, local track evidence, source-time path
  residuals and unknown/partial coverage. See `motion.md`; broader camera models remain future work.
- [x] TB-203: explicit calibration-scoped review policies, exact temporal hysteresis/minimum
  duration, evidence-bounded padding and unknown coverage. See `interpretation.md`; no exclusions.
- [x] TB-204: immutable keep/exclude/review/unknown snapshots, reasoned user overrides/restoration,
  checked parent history and bound chronological preview plans. See `decisions.md`.
- [x] TB-205a: versioned duration-weighted evaluation harness, rights/label/split validation,
  unknown/disagreement accounting and synthetic negative controls. See `quality-evaluation.md`.
- [ ] TB-205b: obtain rights-cleared held-out camera labels and evaluate static product shots,
  deliberate pans, night scenes and actual focus failures. M2 accuracy gate remains open.

Exit: measured per-defect precision/recall and normal-footage exclusion time; all exclusions can be
restored; no deletion/source modification; movement and staticness alone cannot force an exclusion.
Automatic exclusions remain opt-in until held-out results justify a specific supported defect class.

## M3 — Meaningful event candidates

- [ ] TB-301: cached image embeddings for relevance and duplicate-take proposals.
- [ ] TB-302: one optional local VLM adapter with structured output, revision/license manifest,
  sparse screening and dense event reinspection.
- [ ] TB-303: action start/execution/result windows; long/short trim alternatives and completeness.
- [ ] TB-304: combine semantic relevance, completeness and quality without treating ranks as probabilities.
- [ ] TB-305: benchmark uniform sampling, motion-only and semantic selection under equal budgets.

Exit: held-out event coverage and action truncation results, including fast/occluded events; bad
model IDs/ranges are rejected; missing models report reduced capability; no mandatory cloud account.

## M4 — Multi-source first cuts and review (public alpha target)

- [ ] TB-401: chronological baseline with mandatory events, duplicate alternatives and duration budget.
- [ ] TB-402: explicit role/dependency constraints and infeasibility reports; deterministic tie-breaking.
- [ ] TB-403: multiple-source timeline execution, explicit audio policy, preview and OTIO export.
- [ ] TB-404: minimal local review UI: source jump, reasons, restore/trim/replace/order overrides.
- [ ] TB-405: editor study comparing end-to-end correction time with manual editing and simple baselines.

Exit: a licensed multi-take example goes from ingest to editable/rendered draft; no silent hard
constraint violations; mandatory events and provenance retained; user corrections survive replanning;
independent editors can inspect and correct output using documented steps.

## M5 — Validate, harden and widen

- [ ] Add constrained optimization only where it improves measured baseline failures.
- [ ] Optional music alignment within action-preserving trim limits; ambient-audio continuity.
- [ ] Test target-editor interchange paths and describe unsupported effects/metadata.
- [ ] Validate model/media paths across hardware; package with a resolved third-party inventory.
- [ ] Add a cross-platform dependency lock and automated, reviewed tool/action updates before release.
- [ ] Add preference ranking from opt-in editor feedback; split datasets by shoot/project.
- [ ] Extend genres after evaluating errors and collecting appropriate labels.

Exit: published supported-platform matrix, reproducible evaluation report, license inventory,
failure examples and release artifact checks. No unattended-editing quality claims without evidence.

## Sequencing and effort assumptions

One experienced developer's initial planning range for M1–M4 is roughly 9–14 developer-weeks,
including initial fixture collection and evaluation. This is an estimate, not a delivery commitment.
Model hardware, footage rights and a review UI can move it substantially. Re-estimate after M1.

The first release does not include a new foundation model, a full NLE, distributed processing,
automatic video generation, or every genre. Each milestone should land a working vertical slice.
