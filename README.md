# Takebraid

**Turn raw footage into a considered first cut.**

[한국어](README.ko.md) · [Architecture](docs/architecture.md) · [Roadmap](docs/roadmap.md)

Takebraid is a planned local-first assistant for editing footage with little or no dialogue.
It will find meaningful moments, flag unusable sections, and assemble an editable rough cut
from multiple takes. The original media stays intact, and every proposed cut should be traceable
to its source and evidence.

## Current status

**Pre-alpha. Metadata ingest and decoded timing inspection are available; automatic editing is not yet implemented.**

| Available now | Planned |
|---|---|
| `takebraid ingest`: read-only metadata and SHA-256 identity | Manual timeline and proxy generation |
| Versioned project registry, relinking and checked scan cache | Preview rendering and audio alignment |
| `takebraid scan`: decoded PTS maps, timing diagnostics and boundary validation | Quality/content analysis |
| Installable Python package and `takebraid doctor` | Quality analysis and reversible exclusions |
| Exact source-time values and invariant tests | Event selection and multi-take assembly |
| CI, contribution guide and architecture decisions | Review UI and timeline interchange |
| Development and evaluation plan | Cut planning and FFmpeg rendering |

The initial target is dialogue-free process/product footage, with chronological assembly and
human review. Other genres follow evidence from that first use case.

## Development quick start

Python 3.11+ is required. FFmpeg and ffprobe are external tools needed for future media processing;
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
