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
| NumPy 2.3.5 | Optional encoder numeric arrays; not bundled | BSD-3-Clause plus wheel third-party notices; https://github.com/numpy/numpy/tree/v2.3.5 |
| ONNX Runtime 1.31.1 | Explicit optional CPU provider; not bundled | MIT plus bundled/transitive notices; https://github.com/microsoft/onnxruntime/tree/v1.31.1 |
| ONNX 1.23.2 | Optional development-only graph oracle generator; not bundled | Apache-2.0; https://github.com/onnx/onnx/tree/v1.23.2 |
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

## Optional local checkpoints

No pretrained checkpoint is selected or redistributed. Each user-supplied model manifest declares
its content hash, model revision, source, license and permitted use independently of runtime terms.
The generated channel-mean oracle is original Apache-2.0 project code, not learned weights or a
semantic benchmark; its generated model stays outside Git. Optional runtime telemetry is disabled
before owned import; see [the encoder guide](docs/local-embeddings.md). Transitive packages
(flatbuffers, protobuf, and development ml_dtypes/typing_extensions) retain their own terms; they
are installed by the explicit extra, not bundled into the core wheel.
