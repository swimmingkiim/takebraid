# Prediction-hidden local annotation (TB-205c)

The pilot has one AI reviewer, not independent human evidence. This checkout tool prepares a concrete
human review handoff without pretending that additional annotators already exist. It exports camera
entries only; controlled synthetic labels remain constructed. It does not complete the M2 accuracy
gate, acquire new natural-positive footage or establish reviewer identity.

## Export

From an installed development checkout with FFmpeg/ffprobe:

```bash
python -m tools.blind_review export workspace/labeled-pilot/sample-v1/manifest.json \
  --output workspace/blind-review-pilot
```

The destination must be new. Only `workspace/blind-review-pilot/review/` is the reviewer packet.
Open its `index.html` in a normal local browser; no server, account, installation or network is
needed. Send/copy that folder manually only when the source rights permit the intended sharing.
The tool does not send messages, upload footage or start a server. The sibling `binding.json`
belongs to the evaluation operator: keep it and the evaluation dataset away from reviewers.

The packet contains every decoded frame as PNG, opaque task/media identifiers, target defect,
source/map/image hashes, exact signed PTS boundaries and rational clocks, media-tool versions and
attribution. Source images are downscaled to at most a 512-pixel edge, without upscaling, frame
sampling, FPS normalization or display-transform repair. Unsupported clocks, HDR/wide gamut,
rotation and other analysis limitations fail explicitly. A packet is bounded to 5,000 unique
decoded frames and the evaluation manifest's 200-entry limit. Existing source files are read-only.
Only validated camera sources are extracted; no original movie, source locator, previous label,
annotator identity, split, policy, measurement or prediction is copied into the review packet.
The source rights declaration is retained verbatim; operators should ensure it does not reveal
labels. Attribution/source identity can reveal scene context. This is a workflow for hiding prior
answers, not a cryptographic blind study or access-control system.

## Review independently

Each person uses their own copy and reviewer ID. Review the frames in order with the slider or
previous/next controls. Add adjacent `[first_frame, end_frame)` intervals until the final frame
boundary is covered. Choose explicitly:

- `normal`: no visible target defect at this review resolution, considering the scene context.
- `defect`: the target defect is visible with adequate evidence.
- `unknown`: insufficient evidence, ambiguous intent, atmospheric softness or another uncertainty.

Use the target-specific guidance and agree on a protocol before collecting a study. Changing the
protocol after viewing test predictions invalidates a held-out claim. All frame inspection is the
reviewer's responsibility; the UI's completion counter counts interval coverage, not attention.
There is no automatic all-normal label. Undo removes the latest interval for that task.

Draft JSON can be saved and reopened. It is not accepted as a completed review. A final JSON needs
complete coverage, a valid ID and explicit independent-human attestation. Reopening JSON clears the
attestation checkbox. Nothing is automatically saved or uploaded; keep the exported JSON before
closing the page. The software cannot verify that an ID names a real person, that different IDs
are different people, or that a reviewer has not seen predictions. A reviewer who has already seen
the AI pilot labels cannot retrospectively provide blind validation for those clips.

## Collect and evaluate

After actual independent reviewers return JSON files:

```bash
python -m tools.blind_review collect workspace/blind-review-pilot \
  --review /absolute/path/reviewer-a.json --review /absolute/path/reviewer-b.json \
  --label-version human-study-v1 --output workspace/human-study-manifest.json
python -m takebraid evaluate workspace/human-study-manifest.json \
  --output workspace/human-study-evaluation --split test
```

Collection requires 2..10 distinct IDs, a matching packet hash and explicit human/independence
attestations. Every task needs a complete ordered integer frame partition; gaps, overlaps, boolean
indices, missing tasks and blank truths are rejected. Packet/image hashes, the frozen original
manifest, actual source identity and decoded frame clock are checked again. No existing manifest
is replaced. A fresh label version and separate output keep the AI pilot intact.

Boundaries from different reviewers are merged into a common partition. Each interval retains each
person's vote. Differences become unknown consensus in the existing evaluator, with disagreement
duration separately counted; a majority vote never silently deletes dissent. The output retains
constructed entries and frozen policies/splits, changes only camera label provenance/votes, and
records packet/review digests. Absolute local artifact references allow output outside the dataset;
this collected manifest is an operator artifact, not a portable reviewer packet. It can contain
private paths and should not be published without inspection.

Human review of these clips still cannot establish natural-defect recall: the original pilot has
no confirmed natural positive failures. Add permitted naturally occurring defects and new shoots,
freeze the protocol/acceptance criteria, and keep source groups separated before an accuracy claim.
No annotation operation changes exclusions, predictions or source content.

## Validation record and limits

The prepared local handoff is `workspace/blind-review-pilot-v2/review/index.html`: 3 CC0 source
excerpts, 150 unique PNG frames, 6 camera/defect tasks. No human review has been collected. The
operator who developed this pilot has already seen its AI labels and is not an independent rater.
The reviewer-only archive is `workspace/takebraid-blind-review-pilot-v1.zip`; it excludes the private
binding and evaluation artifacts. Checksums and measured limits are in
[the validation summary](validation/blind-review-summary.json).

Automated generated-signal tests exercise export → simulated JSON collection → actual evaluation,
retain disagreement duration, reject changed images and duplicate raters, and verify negative-start
and VFR source indices against the existing independent clock oracle. Simulated human metadata in
these tests verifies the format contract only; it is not human accuracy evidence.
`node tools/check_blind_review.cjs` optionally checks synthetic UI handlers for frame navigation,
interval validation, undo, final/draft export and restore. Node is not a runtime/core dependency.
The HTML blocks network connections and embeds task data so opening it needs no JSON fetch.

Actual browser visual/download QA remains unverified. The earlier automation browser rejected
local `file://` navigation. On 2026-10-30, the browser inventory reported local browser use disabled
in Work settings; no browser interaction or download check was performed. The mock-DOM handlers
passed again, but do not prove rendering, image loading, file-origin CSP behavior or download
compatibility. Next: with browser access available, inspect this packet in a normal local browser,
verify image/navigation/interval controls and draft download/restore, and confirm incomplete or
unattested final reviews are rejected. Do not attest an AI check as independent human labeling.
