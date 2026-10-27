# Reversible editing decisions (TB-204)

`takebraid decisions` records user choices and turns them into a checked manual preview plan.
Originals, observations, interpretations and previous edits stay intact. No source file is deleted.

```bash
# interpretation.json and quality.json are the saved TB-203/TB-201 outputs.
takebraid decisions create <interpretation.json> --asset <asset.json> --observation <quality.json>
takebraid decisions show <decision.json> --asset <asset.json>
takebraid decisions set <decision.json> --asset <asset.json> \
  --frames 20:35 --state exclude --reason "Chosen range is not needed in this draft"
# Each edit prints a NEW decision.json path. Use that returned path for subsequent work.
takebraid decisions restore <edited-decision.json> --asset <asset.json> \
  --frames 20:35 --reason "Restore inclusion and original review context"
takebraid decisions plan <edited-decision.json> --asset <asset.json> --fps 25 --audio mute
takebraid render <returned-timeline.json> --project ./workspace/demo
```

Replace the frame range with valid decoded source indices. `FIRST:END` is half-open and must satisfy
0 ≤ FIRST < END ≤ frame count. These are not seconds or average-FPS-derived coordinates. The optional
source audio mode is `--audio source --audio-stream 1` (use the actual absolute audio stream index).
The existing preview preset, output-clock rounding and geometry/audio limits apply; see `previews.md`.

## Baseline and explicit changes

A new snapshot covers every source frame, including its final presentation end:

| State | Meaning | Preview inclusion |
|---|---|---|
| keep | Retain in this editing baseline; no positive quality assertion | Included |
| review | Inside a padded temporal candidate; inspect its original evidence | Included |
| unknown | Missing/unsupported measurement or explicit user uncertainty | Included |
| exclude | Explicit reasoned user exclusion | Omitted |

Creation never promotes a candidate to exclusion. Padded candidate ranges become review, unknown
cells remain unknown, and remaining frames are kept. Overlapping review proposals are combined only
for this decision partition; the frozen interpretation retains separate cores and evidence indices.
A ready decoded map is required; unknown timing cannot safely define an editable source partition.

`set` accepts keep/exclude/review/unknown and a nonempty reason (up to 1,000 characters). Overrides
apply in order, with the last one winning within its range. Each output interval retains its baseline
state and last override index, so explicit keep over an unknown/review baseline remains inspectable.
An override does not change the measurement, original candidate or prior decision record.

`restore` reapplies the **frozen baseline** in the selected range: a reviewed candidate becomes review
again, an unmeasured frame becomes unknown again, and other frames become keep. All are included
in the preview. Restore is not undo of the immediately preceding edit; choose an older snapshot to
continue another branch or recover a prior set of choices. It may span multiple states and does not
remove override history. New analysis/policy results do not silently retarget an existing record.

## Records and validation

Snapshots live at `decisions/<UUID>/decision.json` and are published as new files. They contain:

- Schema/kind/recipe `reversible-decisions/1`, asset/stream and exact source time base.
- Project-relative observation/interpretation paths and hashes; the interpretation embeds its policy.
- A parent path/hash, cumulative ordered override operations and derived full-coverage intervals.
- Interval frame/PTS bounds, resolved state, original baseline state and applicable override index.

The original observation, not a copy outside the project, is required on create. Full observation and
interpretation validation checks completed receipts, source/map/tool identity and recomputed temporal
results. The original policy file is unnecessary because the checked interpretation preserves the
normalized policy and original policy digest. Current tool revisions must match the frozen evidence;
see `interpretation.md` for this conservative compatibility rule.

Every load follows at most 100 override revisions plus the initial snapshot, verifies parent hashes,
source/provenance consistency and exactly one appended operation per revision, and replays the leaf
intervals. Derived interval edits, substituted evidence, broken parents, wrong-project paths and
changed sources are rejected. Parent records are preserved; there is no implicit mutable “latest”
pointer. A failed/cancelled publication preserves earlier records. Snapshots are atomic single-file
user edits rather than cached analysis stages; they do not have analysis execution receipts.
Checksums/replay establish consistency, not cryptographic authorship or tamper-proof local storage.

## Checked timeline and actual preview

`decisions plan` merges adjacent included intervals into chronological runs, retaining keep/review/
unknown and dropping only exclude. It does not reorder or infer missing frames. All-excluded output
and more than 64 included runs fail before a timeline is created. Cuts must also survive the existing
output-frame rounding rules; a very short kept run can require a higher output FPS.

The new timeline binds the exact decision path/hash. Rendering and cache reuse revalidate its complete
evidence/history and require its cuts to equal the included runs. Dependency mutation during rendering
prevents a completed receipt. Decision previews use `decision-preview/1`; generic manually created
plans retain `manual-preview/1`. Output still undergoes decoded frame/time/audio verification.

Plans and rendered attempts are retained. An edit after a preview creates another snapshot and plan;
it does not silently update an old preview. To review restored footage, generate a new plan from the
restored snapshot. Manually authored plans remain a separate explicit workflow.

Command success exits 0; invalid records/ranges, exhausted limits, source/tool/publication or preview
errors exit 1; interruption exits 130. Unlike observation/interpretation coverage, a decision's
unknown/review inclusion is an explicit editing baseline, so showing/planning it does not exit 2.
No automatic exclusion policy or quality classification is added in this slice.

## Evidence and next boundary

Pure fixtures check full keep/review/unknown coverage, signed bounds, latest override precedence,
restoration of warnings, range/history limits and empty output rejection. Actual indexed FFV1 sources
verify exclusion picture order and PCM impulses, restoration of all source pictures, sparse unknown
coverage, original preservation, parent/interval/cut tampering, source mutation and cancellation.
Render-time dependency mutation produces a failed attempt; a cached preview still rechecks its bound
snapshot. A pre-existing TB-203 interpretation cache remains reusable after helper extraction.

TB-205 evaluates defect accuracy/intentional footage failure cases with licensed, labeled material;
M4 still owns a review UI and multi-source first cuts. Synthetic source/clock tests do not establish
editorial usefulness or calibrated unattended-editing quality.
