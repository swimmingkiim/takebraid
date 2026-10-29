# Labeled public camera-derived sample pilot

PR #12 is merged. This follow-up supplies actual labeled samples and a completed pilot run: three
CC0 source videos, nine two-second grayscale FFV1 clips, 450 reviewed sample frames and 12 evaluation
entries. Original clips have separate focus/exposure entries; controlled variants each target one
metric. Downloads and generated media stay outside Git under ignored `workspace/labeled-pilot/`.
Tracked source hashes, annotations and reconstruction tooling live in `examples/labeled-pilot/` and
`tools/labeled_pilot.py`.

## Sources and review

- [Mma Legage Waterfall video](https://commons.wikimedia.org/wiki/File:Mma_Legage_Waterfall_video.webm),
  Kbmotswagole, CC0: the predeclared 10..12 second range avoids the edited title animation. Calibration only.
- [StreamOfFlowingWater](https://commons.wikimedia.org/wiki/File:StreamOfFlowingWater.webm), Patjos.scot,
  CC0: first two seconds retain detailed grass/rocks and natural water motion. Test group.
- [Water flowing strem](https://commons.wikimedia.org/wiki/File:Water_flowing_strem.webm), BhotaRohit,
  CC0: first two seconds retain atmospheric haze as an uncertain-focus control. Test group.

Full source URLs, authors, permission pages and SHA-256 values are pinned in sources.json. The files
are camera-derived public footage, not asserted untouched camera originals; encoding/editing already
present in the uploads is retained. Samples are resized to a maximum 320-pixel edge, converted to
8-bit gray, normalized to 25 fps/50 frames and stripped of audio. These sample-resolution judgments
must not be generalized to native-resolution optical focus or sensor exposure.

One AI reviewer inspected all selected original frames via contact sheets and full-resolution source
examples, then checked all six controlled-variant sheets. Final regenerated clips were verified to
have identical decoded grayscale bytes to the 450 visually reviewed frames. Labels were established
before observing predictor outputs. This is `assistant_review`, not a fabricated pair of human
annotators. Original rock/grass detail is normal for global focus in the reviewed ranges; natural
water motion and letterbox bars are not labeled failure. Hazy focus is unknown because atmospheric
softness cannot confidently be separated from optical defocus by this review. These are subjective
pilot judgments with retained rationale, not independently adjudicated ground truth.

For each source, blur (`gblur`, sigma 6) and darkening (luma ×0.04) are applied only to frames [15,35).
Their active intervals are constructed labels, not naturally captured focus/exposure failures.
Outside the interval they inherit original labels, including hazy unknowns. The sample license is
CC0-derived media; project labels/recipes are Apache-2.0. No private workspace footage is used.

## Calibration and results

Only the mma source group calibrates thresholds. Focus entry is the midpoint between minimum normal
Laplacian variance and maximum controlled-blur variance in that calibration group; exit is halfway
back toward the normal bound. Exposure entry/exit are analogously derived from normal/dark fractions.
Rationals are bounded to the explicit policy schema. Test source measurements are generated only
after policy hashes are locked. Labels/source recipes/manifest/clips are checksum-locked on reruns.
The program enforces source/project grouping but does not claim cryptographic preregistration.

The 8 test entries comprise 4 original-camera evaluations and 4 controlled-variant evaluations:

| Test evidence | Result in this pilot |
|---|---|
| AI-reviewed original focus | No false positives on the 2 seconds labeled normal; the other 2 seconds are unknown truth |
| AI-reviewed original global exposure | No false positives on 4 seconds labeled normal |
| Controlled blur | All 1.6 seconds of constructed positive time detected; no false positives on determinate normal time |
| Controlled darkening | All 1.6 seconds of constructed positive time detected; no false positives on normal time |

Original-camera entries contain **no confirmed natural positive defects**, so their defect recall and
precision are null rather than 100%. Controlled positive results are not natural-camera accuracy.
There are only two test source groups and one AI reviewer; no confidence bound or release target is
satisfied. `automatic_exclusion_validated` stays false and the independent-human M2 gate stays open.

Evaluation recipe `quality-evaluation/2` adds explicit single-assistant review and single constructed
oracles while retaining at least two raters for human validation. Cohorts are separated by media
kind, label method and defect. Old v1 reports remain historical evidence; they are not rewritten.

## Reproduce and inspect the data

```bash
python -m tools.labeled_pilot download --source-dir workspace/pilot-sources
python -m tools.labeled_pilot prepare --source-dir workspace/pilot-sources --output workspace/pilot-new
# Inspect the 10x5 contact sheets and frozen label rationale before running predictions.
python -m tools.labeled_pilot run --dataset workspace/pilot-new
python -m tools.labeled_pilot pack --dataset workspace/pilot-new --output workspace/pilot-new.zip
```

Download is explicit, size-bounded and checksum-verified. No network use occurs on import, normal
evaluate or rerun. Prepare requires a fresh directory. The package README documents inspection,
policy locks, source relinking after extraction and regeneration with another tool build. Larger
original downloads and FFmpeg binaries are not included in the sample archive.

The prepared local archive is `workspace/labeled-pilot/takebraid-labeled-pilot-v1.zip`; labels,
contact sheets, decoded frame digests, frozen policies, original provenance and complete reports are
inside. A compact public result summary is in `docs/validation/labeled-pilot-summary.json`. Neither
package nor report sends data to a remote application. Generated provenance can retain local paths.

## What remains

Add independently reviewed human labels and naturally occurring positive defects across more shoots,
static products, deliberate camera motion, low light and other genres. This pilot covers focus and
global darkness; it does not evaluate unwanted camera motion or arbitrary editorial intent. Human
annotators must inspect source material independently of predictor output, retain disagreement and
freeze acceptance criteria before a larger test. The sample and tooling make that next review
concrete without presenting an AI-assisted pilot as completed human validation.
