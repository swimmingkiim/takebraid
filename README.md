# Takebraid

**Turn raw footage into a considered first cut.**

[한국어](README.ko.md) · [Architecture](docs/architecture.md) · [Roadmap](docs/roadmap.md)

Takebraid is a planned local-first assistant for editing footage with little or no dialogue.
It will find meaningful moments, flag unusable sections, and assemble an editable rough cut
from multiple takes. The original media stays intact, and every proposed cut should be traceable
to its source and evidence.

## Current status

**Pre-alpha. Ingest, timing inspection, manual cut previews and focus/exposure measurements are available; automatic selection is not yet implemented.**

| Available now | Planned |
|---|---|
| `takebraid ingest`: read-only metadata and SHA-256 identity | Event/content interpretation |
| Versioned project registry, relinking and checked scan cache | Automatic event selection and assembly |
| `takebraid plan` / `render`: saved manual cuts and verified MOV previews | Multi-source timelines, MP4 delivery presets |
| `takebraid scan`: decoded PTS maps, timing diagnostics and boundary validation | Motion/defect interpretation |
| `takebraid quality`: focus/exposure observations with ROI and exact source PTS | Defect calibration and reversible exclusions |
| `takebraid motion`: background translation candidates, diagnostics and path residuals | General camera motion, segmentation and shake classification |
| `takebraid interpret`: explicit temporal review policies with unknown coverage | Calibrated defect interpretation |
| `takebraid decisions`: reversible user exclusions/restoration and bound preview plans | Review UI and calibrated automatic exclusions |
| `takebraid evaluate`: duration-weighted labeled evaluation and split audits | Held-out camera accuracy validation |
| Prediction-hidden offline annotation packets and disagreement-preserving vote collection | Independent human study and browser visual QA |
| `takebraid visual`: cached spatial features and sampled frame-match proposals | Learned image embeddings and duplicate-take validation |
| `takebraid embed`: explicit local ONNX image encoder and provenance-bound cache | Qualified learned checkpoints and embedding retrieval |
| Installable Python package and `takebraid doctor` | Optional local model adapters |
| Exact source-time values and invariant tests | Event selection and multi-take assembly |
| CI, contribution guide and architecture decisions | Review UI and timeline interchange |
| Reproducible synthetic media matrix with independent timing/content expectations | Real-camera validation |

The initial target is dialogue-free process/product footage, with chronological assembly and
human review. Other genres follow evidence from that first use case.

## Development quick start

Python 3.11+ is required. FFmpeg and ffprobe are external tools needed for media processing;
they are not bundled. Basic package tests require neither models nor media tools.

```bash
git clone https://github.com/swimmingkiim/takebraid.git
cd takebraid
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
takebraid --version
takebraid doctor
python -m pytest
```

On Windows use `python -m venv .venv` and `.venv\Scripts\Activate.ps1` in PowerShell.
`doctor --json` emits machine-readable tool paths and exits 1 when either media tool is missing.
It checks executable availability, not codecs or runtime compatibility.

Inspect a video with `takebraid ingest ./raw/clip.mov --project ./workspace/demo`.
This saves versioned metadata without modifying the source. Then run
`takebraid scan <asset.json> --stream 0` to inspect decoded presentation timestamps.
See [ingest](docs/ingest.md) and [frame-map usage and limitations](docs/frame-maps.md).
Use `takebraid project show ./workspace/demo` to inspect the registry and `project verify` to
check source content. Repeated scans reuse validated results; `scan --force` preserves a fresh
attempt. See [projects, relinking and cache rules](docs/projects.md).

Create a manual draft with `takebraid plan <asset.json> --stream 0 --cut 0:5 --fps 25 --audio mute`,
then `takebraid render <timeline.json> --project ./workspace/demo`. Cut indices are decoded source
frames, with an exclusive end. See [preview/audio/rounding policies](docs/previews.md).

Reproduce the [synthetic media validation matrix](docs/media-validation.md) with
`python -m tools.media_validation --output workspace/media-validation`.

Measure [focus/exposure observations](docs/quality.md) with
`takebraid quality <asset.json> --stream 0 --size 160 --every 5`. These are measurements,
not automatic exclusion decisions.

Measure [background motion candidates](docs/motion.md) with
`takebraid motion <asset.json> --stream 0 --size 96 --every 1`. Tracking uncertainty remains explicit.

Apply an explicit [temporal candidate policy](docs/interpretation.md) with
`takebraid interpret <quality.json> --asset <asset.json> --policy ./policy.json`.
Candidates retain evidence and unknown coverage; they do not change a timeline.

Record [reversible decisions](docs/decisions.md), explicitly exclude/restore frame ranges, and
create a preview plan. Review and unknown footage stays included until a user excludes it.

Run the [labeled evaluation harness](docs/quality-evaluation.md) with
`takebraid evaluate <manifest.json> --output workspace/evaluation`. Synthetic controls are separate
from camera evidence; M2 camera validation remains pending.

A [labeled camera-derived pilot](docs/labeled-pilot.md) includes CC0 source provenance, single-AI
review labels, controlled distortions and reproducible split-separated evaluation. It is not a
substitute for independent human validation.

A [prediction-hidden offline annotation tool](docs/blind-review.md) prepares human review packets
and collects distinct reviewer votes without erasing disagreement. Actual independent human
validation and local-browser visual QA remain pending.

Find [spatial visual-match candidates](docs/visual-matches.md) with `takebraid visual observe` and
`visual compare`. This dependency-free baseline compares grayscale cell means, not semantic events
or whole takes; it cannot automatically exclude footage.

Run an explicitly selected [local ONNX image encoder](docs/local-embeddings.md) with
`takebraid embed <asset.json> --stream 0 --model <model.json>`. Optional dependencies and a compatible
local model are required; no model is downloaded and no semantic accuracy is yet validated.

## Design commitments

- An editable first cut with evidence and uncertainty attached to each decision.
- Exact media time and source preservation before sophisticated model behavior.
- A deterministic planning/execution core with replaceable, optional model adapters.
- Local processing by default, explicit opt-in for remote inference.
- Small end-to-end releases, evaluated on actual unedited footage.

See [system design](docs/architecture.md), [design philosophy in Korean](docs/design-philosophy.ko.md),
[data contracts](docs/contracts.md), and [evaluation](docs/evaluation.md).

## Contributing and licensing

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and milestone M1 in the [roadmap](docs/roadmap.md).
The project code is licensed under Apache-2.0. Third-party tools, models and datasets retain
their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
