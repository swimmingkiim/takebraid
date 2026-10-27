# Third-party inventory

The Takebraid code license does not relicense dependencies, models, datasets or system binaries.
No model weights, datasets or FFmpeg binaries are distributed by this bootstrap repository.

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
