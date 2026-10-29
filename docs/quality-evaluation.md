# Quality evaluation harness (TB-205a)

`takebraid evaluate manifest.json --output workspace/evaluation --split test` scores fixed temporal
candidate policies against explicit source-frame labels. It does not fit thresholds or validate an
automatic exclusion policy. Rights-cleared, independently labeled camera footage is still needed to
complete TB-205b; M2's camera-accuracy gate remains open. A small public camera-derived, single-AI
review pilot is now available in `labeled-pilot.md`; it is not independent human validation.

## Reproduce the synthetic controls

From a development checkout with FFmpeg/ffprobe:

```bash
python -m tools.evaluation_fixture --output workspace/quality-controls
```

A clean macOS run of commit `11c8c5e` is preserved in
`docs/validation/quality-controls-macos.json`, including exact tools and expected false-positive
controls. CI reruns the four controls and publishes its report with media evidence.

Use a new output directory. The recipe creates original Apache-2.0 signals, pinned policies, real
quality/motion/interpretation artifacts, constructed labels and an evaluation report. It asserts
independent expected outcomes: low-texture static and intentionally dark controls produce false
positives, constructed blur is detected, and a constant pan has unknown residual coverage at its
endpoints. These are regression/failure controls, not camera accuracy measurements. The two oracle
voter IDs denote constructed votes, not human editors. No external data or models are downloaded.

For an existing dataset, run `takebraid evaluate <manifest.json> --output <directory>`; `--split`
selects test (default) or calibration. `--force` preserves a new attempt. Exit 0 means a consistent
report was produced, not that an accuracy target passed. Invalid inputs exit 1; interruption exits
130. The report always records `automatic_exclusion_validated: false` in this initial harness.

## Manifest contract

Version 0.1 has dataset_id, label_version, policy_registry and entries. Example shape:

```json
{
  "schema_version": "0.1",
  "dataset_id": "my-reviewed-corpus",
  "label_version": "editors-v1",
  "policy_registry": {"focus_failure": "<64 lowercase hex SHA-256 of the policy file>"},
  "entries": [{
    "id": "clip-a", "kind": "camera", "label_method": "human", "split": "test",
    "project_id": "shoot-project-a", "shoot_id": "shoot-a", "scene": "static-product",
    "defect": "focus_failure", "asset": "project/assets/.../asset.json",
    "observation": "project/stages/.../quality.json",
    "interpretation": "project/stages/.../interpretation.json",
    "annotators": ["editor-a", "editor-b"],
    "annotation_protocol": "Independent source-frame judgments, blinded to predictions; disagreement retained",
    "rights": {
      "source": "Owner/provenance reference", "license": "Applicable terms",
      "permission_evidence": "Consent/license record reference", "evaluation_permitted": true
    },
    "labels": [{"first_frame": 0, "end_frame": 100,
                "votes": {"editor-a": "normal", "editor-b": "unknown"}}]
  }]
}
```

Paths resolve against the original manifest directory and must be local. The optional `decision`
path evaluates explicit user exclusions from that same interpretation. Asset/observation/
interpretation/decision integrity is checked using existing loaders and source hashes. Unsupported
source timing fails rather than inventing duration or silently dropping an entry.

Supported defect mappings: laplacian_variance → focus_failure; dark_fraction/bright_fraction →
exposure_failure; path_residual_squared → unwanted_camera_motion. This is the experiment's intended
target, not proof the feature identifies that defect. Each class pins one policy digest per manifest;
use separate experiments for alternative policies. Test labels are never used to select thresholds.
A hash declaration is not cryptographic preregistration or proof that a person avoided test leakage.

Every entry declares synthetic/constructed, camera/human, or camera/assistant_review. Human validation
still requires at least two distinct annotators; assistant_review requires exactly one explicitly
identified AI reviewer; constructed oracles may have one or more votes. All declared votes are required
for every interval. A single vote is not independent consensus. Votes are defect, normal or unknown. Only unanimous
normal/defect votes are determinate; disagreement or any unknown yields unknown truth. Labels must
partition all decoded frames with exclusive ends. Annotate source intent as well as visible defects:
static product views, deliberate pans and intentional darkness are essential normal controls.
The program validates declarations/structure, not human independence or legal ownership.

Across the entire inventory, project IDs, shoot IDs and exact asset identities cannot cross
calibration/test splits. Duplicate source/defect entries are rejected. This audits declared groups
and exact identities; it does not detect undeclared related shoots, near-duplicates or cropped copies.
Selected sources/artifacts and label partitions are fully verified; unselected entries participate
in metadata/split audits but are not scored. Limits are 200 entries, an 8 MiB manifest and 250,000
selected frame evaluations in total.

## Defined metrics (`quality-evaluation/2`)

All accounting uses exact source-frame presentation durations, including signed PTS, VFR and final
ends. These are **duration-weighted** precision/recall, not event matching or frame-count accuracy.
Candidate **cores** are positives; padded review ranges are not labeled defective. Known cells
outside accepted cores are clear; unmeasured/unreliable cells remain prediction unknown.

- Precision = TP/(TP+FP), restricted to determinate human/constructed labels.
- Recall over all labeled defect time = TP/all labeled defect duration. Abstaining on defects lowers it.
- Observed-defect recall = TP/(TP+observed FN), reported alongside unknown-on-defect duration.
- Observed-normal false-positive rate = FP/(FP+TN); unknown normal time is separately visible.
- Label/prediction unknown rates, disagreement frames/time and candidate time on unknown truth are retained.
- Explicit user-decision exclusions are scored separately: excluded normal/defect/unknown-label time.
  Normal exclusion rate uses labeled normal duration only in entries that actually supplied decisions.
  Without decision coverage its denominator is zero and the ratio is null, not a perfect zero score.

Zero denominators produce null. Cohorts sum duration counts before calculating ratios. Reports retain
per-entry, per-project and per-scene results and sample/project/shoot counts. Synthetic/camera and human/assistant/constructed review levels are never pooled into one score. An entry's declared kind is not authenticated camera origin.
No confidence interval or minimum sample-size release guarantee is claimed by this slice.

## Provenance and publication

Reports bind the original manifest/label bytes, label version, pinned policy digests, validated
source/map/observation/interpretation/decision hashes, method settings, full tool build configurations,
Python/platform and declared split counts. Cache reuse verifies its receipt/checksum, manifest
snapshot and recomputed score. Mutations prevent completion; failure/cancellation leave terminal
receipts. Sources and prior reports are unchanged.

A preserved attempt stores evaluation.json, the original manifest bytes and manifest-origin.json
with the original resolution directory. The snapshot's relative paths still refer to that original
base; rerun the original manifest or relocate its paths explicitly. The local manifest/origin can
contain private paths. Artifact reference paths are omitted from the score report, while declared
rights/protocol text is retained. Sharing is a separate user action; this command has no network use.

## Camera evaluation still required (TB-205b)

A small CC0 camera-derived pilot has been labeled by one AI reviewer; its original camera clips
contain no confirmed naturally captured positive focus/exposure failures. It does not supply the
independent human-labeled camera corpus needed for M2 sign-off. Public
quality datasets are cataloged in `evaluation-data.md`; global opinion scores do not establish our
source-frame defect/normal labels. Before M2 sign-off: acquire permitted material, preserve independent
editor votes, split by shoot, freeze calibrated policies/release targets before test evaluation, run
the camera cohort, and publish sample sizes, uncertainty and failure cases. Do not promote this
synthetic regression report to a real-camera or unattended-editing accuracy claim.

## Prepare independent review

The [offline review workflow](blind-review.md) exports camera frames without previous labels or
predictions, then collects actual independently declared human votes into a new manifest. It does
not invent additional raters or complete the M2 gate. Preserve the original calibration/policy and
source splits; new naturally defective footage and an independently frozen protocol remain needed.
