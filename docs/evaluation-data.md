# Evaluation data inventory

Review date: 2026-10-29. The original synthetic controls used no external media. The later labeled pilot downloads three
CC0 camera sources listed in `../examples/labeled-pilot/sources.json`; excerpts and controlled
derivatives are packaged locally, with source hashes and attribution. This inventory records candidate sources and remaining annotation
work; it is not a grant of rights or a substitute for checking the exact supplied files/terms.

| Source | Official information | Fit and remaining work |
|---|---|---|
| [LIVE-VQC](https://live.ece.utexas.edu/research/LIVEVQC/index.html) | Authentic-distortion videos with subjective quality scores; the page provides a permission notice with preservation/acknowledgment conditions and a download form | Useful camera-domain diversity. Opinion scores do not supply our source-frame defect/normal consensus; access and independent temporal labeling are still required. |
| [KoNViD-1k](https://database.mmsp-kn.de/konvid-1k-database.html) | Research download and individual quality ratings, with source video IDs and citation instructions | Whole-video quality ratings are not temporal focus/exposure/shake judgments. Preserve source-specific terms and provenance; annotate interval-level intent/defects before evaluation. |
| [YouTube-UGC subjective quality study](https://research.google/pubs/subjective-quality-assessment-for-youtube-ugc-dataset/) | Describes quality opinion scores and full-video/chunk quality relationships | Compression/perceptual-quality evidence does not directly label our defect classes. Verify current per-asset availability/terms and obtain independent temporal labels. |
| Owner-provided originals | No corpus supplied in this task | Record source hashes, evaluation permission, shoot/project grouping and at least two independent editor votes before scoring a camera cohort. |

For each acquired asset, retain exact origin, version/hash, applicable license/permission evidence,
annotation protocol/version and disagreement. Keep original media and restricted labels outside Git;
only publish artifacts allowed by their specific conditions. AI review labels are explicitly marked assistant_review and are not counted as independent human
camera validation. Human validation still requires at least two annotators.

The original project signal recipes in `tools/evaluation_fixture.py` are Apache-2.0. Their labels
are constructed oracle data; the synthetic kind is mandatory and separate from camera evidence.

Independent human review preparation is implemented in [blind-review.md](blind-review.md).
Only the exported review directory is intended for reviewers; the original dataset/binding and
model results stay with the operator. Reviewer identity/independence are self-attested, and no
completed human annotations are bundled or claimed.
