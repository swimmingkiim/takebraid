# Third-party inventory

The Takebraid code license does not relicense dependencies, models, datasets or system binaries.
No model weights, original video downloads or FFmpeg binaries are distributed in Git.
The optional locally generated pilot archive contains CC0-derived clips; its provenance is below.

| Component | Use / status | Terms / source |
|---|---|---|
| Hatchling | Build-time | MIT, https://github.com/pypa/hatch |
| pytest | Development / tests | MIT, https://github.com/pytest-dev/pytest |
| Ruff | Development / lint and format | MIT, https://github.com/astral-sh/ruff |
| build | Development / packaging | MIT, https://github.com/pypa/build |
| FFmpeg / ffprobe | External inspection, decoded timing, quality/motion observations and manual previews; not bundled | Build-dependent LGPL/GPL; https://www.ffmpeg.org/legal.html |

Transitive dependency terms also apply. Before adding a runtime dependency, checkpoint or dataset,
record its version/revision, origin, license and redistribution scope. Generate a resolved inventory
for release artifacts. Planned components are discussed in `docs/research.md`, not approved by
their mention there.

## Optional labeled pilot media

The three pinned public Wikimedia Commons sources are CC0-1.0, with authors,
license pages and checksums in [sources.json](examples/labeled-pilot/sources.json).
Derived clips preserve this provenance; the Takebraid license does not replace their CC0 terms.
Project-authored annotations and reconstruction recipes are Apache-2.0.
See [the pilot record](docs/labeled-pilot.md) for scope, review limits and reproduction.
