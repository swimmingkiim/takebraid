# Labeled camera-derived pilot samples

This package contains 9 two-second grayscale FFV1 clips (25 fps, 50 frames each), contact sheets,
annotations, source attribution/hashes, derivation commands, frozen calibration policies and reports.
There are 12 source/defect evaluation entries: original clips are evaluated for both focus and
exposure, while controlled variants target one defect each. Video frames are from CC0 Wikimedia
sources listed in sources.json; annotations and recipes are Apache-2.0 project material.

Original labels were written by one AI reviewer (`assistant_review`), not two independent humans.
A hazy source's original focus is unknown. Controlled blur/darkening labels are constructed from
known operator intervals, not naturally captured camera failures. No automatic exclusion or release
accuracy guarantee follows from this small pilot.

## Inspect

Read labels.json and derivations.json first. `review/*.jpg` contains 10-column, 5-row contact sheets;
frame index = row*10+column, starting at 0. For blur/dark variants frames [15,35) are modified.
The annotation rationale describes what was observed and what remains unknown. The original Mma
Legage title animation is outside the predeclared 10..12 second selection.

Calibration uses only the mma source group. The flow/mist source groups are test entries. Policies
are locked before test observation generation; experiment-lock.json and manifest-lock.json preserve
those inputs. This is a transparent development pilot, not cryptographic preregistration or blind
independent human validation.

## Reproduce from a Takebraid checkout

```bash
python -m tools.labeled_pilot download --source-dir workspace/pilot-sources
python -m tools.labeled_pilot prepare --source-dir workspace/pilot-sources --output workspace/pilot-new
# Inspect every frame/contact sheet and the committed labels before running predictions.
python -m tools.labeled_pilot run --dataset workspace/pilot-new
```

Downloads are explicit, bounded and SHA-256 checked. Default package import/evaluate never downloads
media. Prepare requires a new directory. Run locks policies from calibration observations only;
reruns verify locked files rather than refitting on test results. Partial experiments should be
regenerated in a new directory. Source acquisition dates/authors are on the linked Commons pages.

If this archive was extracted elsewhere, first run from the matching checkout:

```bash
python -m tools.labeled_pilot relink --dataset /absolute/path/to/labeled-pilot
python -m tools.labeled_pilot run --dataset /absolute/path/to/labeled-pilot
```

Relink verifies source hashes and updates project locators while preserving old registry snapshots.
Frozen observations require the same FFmpeg/ffprobe build. With another build/platform, regenerate
a fresh dataset/observations and record the new run; do not silently substitute tool revisions.
Evaluation/report snapshots can contain original local paths in provenance sidecars.

To create another archive use `python -m tools.labeled_pilot pack --dataset <directory> --output <new.zip>`.
It retains clips and project artifacts, but not the larger original downloads or any tool binary.
