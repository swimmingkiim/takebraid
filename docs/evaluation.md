# Evaluation plan

Success means preserving the right material and reducing actual correction work, not simply
deleting the most footage. No model quality or speed benchmark has been run for Takebraid yet.

## Test layers

1. Fast offline unit tests: exact time, valid ranges, planning invariants, parsers, malformed outputs.
2. Media integration: generated fixtures with known frame/PTS and audio-event ground truth.
3. Model/quality evaluation: opt-in, pinned checkpoints and device information, held-out labels.
4. Editor evaluation: inspectable multi-take drafts, alternatives, restore operations and elapsed work.

Current tests cover layer 1 and metadata-only media integration with generated video/audio.
Decoded maps are checked against known uniform/VFR/offset/B-frame schedules; render/audio alignment
checks remain future work. The environment CLI checks
paths, not FFmpeg codec support. Media and model suites report skipped capabilities explicitly.
Registry/cache tests additionally cover source moves, revision snapshots, lock conflicts, failed
publication, corrupted records, force reruns and cancellation. A real media integration checks
ingest -> scan -> relink -> cached scan -> preserved force rerun.

## Data

Start with 30–50 rights-cleared projects as an exploratory target, with one genre used for the
initial release. This is for failure discovery/calibration, not sufficient evidence for universal
performance. At least two editors label key events, usable intervals, defects, alternatives and
ordering dependencies; retain disagreements. Split by project/shoot, never adjacent clips/frames.

Include static product reveals, intentional pans, fast actions, occluded hands, repeated operations,
negative/nonzero PTS, VFR, rotation and no audio. Synthetic blur/shake helps regression testing but
does not replace actual optical focus failure and real handheld footage.

Public TVSum and QVHighlights can provide research comparisons, but they do not establish multi-take
raw-footage editing quality. Observe data-specific terms; do not silently put restricted annotations
or derived training artifacts into the default distribution. See `research.md`.

## Measurements

| Area | Record |
|---|---|
| Selection | Key-event recall at equal duration budget, precision, tIoU, action truncation, duplicate time |
| Quality | Per-defect precision/recall, normal-footage exclusion duration, critical-event loss, unknown rate |
| Assembly | Required-step coverage, dependency violations, feasible duration error, retained editor choices |
| User effort | Ingest-to-approved-cut time including review, restores and corrections; compare manual baseline |
| Media | CFR cut accuracy, VFR source mapping, duration mismatch, cumulative A/V drift, source integrity |
| Performance | Wall time/source duration, peak RAM/VRAM, cache savings, device/model/input settings |

Compare uniform sampling, motion-only, quality-only, semantic-only and the combined pipeline using
the same target duration and footage. Report project-level distributions and failure cases, not just
the mean or a selected demo. Human judgments need task instructions and randomized presentation.

## Release gates

M1 must establish media correctness before model complexity. Every planner must enforce hard
constraints or return infeasible. For automatic quality exclusion, set a conservative numerical
precision/false-exclusion target with editors before collecting the held-out result; do not pick
thresholds after seeing the test set. Report uncertainty and sample sizes. No universal numeric
quality guarantee is set at bootstrap because the labeled distribution does not exist yet.

Record the experiment config, input manifest, model revision, dependency versions, hardware,
label version and raw per-project metrics with each result. Data sharing requires explicit rights.
