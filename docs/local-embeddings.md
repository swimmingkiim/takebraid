# Explicit local ONNX image embeddings (TB-301b)

`takebraid embed` runs a user-selected local image encoder and saves source-clock-bound, L2-normalized
vectors. The core installation still has no model dependency. No checkpoint is selected, bundled or
downloaded; the caller supplies a permitted single-file model and a pinned manifest. This delivers
model inference/cache plumbing, not validated semantic relevance, duplicate-take selection, a VLM,
automatic exclusions or M3 sign-off. M2 independent human validation remains open.

## Install and run explicitly

```bash
python -m pip install '.[onnx]'
takebraid embed /absolute/path/asset.json --stream 0 \
  --model /absolute/path/model/model.json --every 25
```

The optional extra pins NumPy 2.3.5 and ONNX Runtime 1.31.1; the core retains Python 3.11+ support.
Wheel/platform availability also constrains the optional provider. The local validation uses macOS
arm64/Python 3.14 and a dedicated Ubuntu 24.04/Python 3.11 CI job. CPU execution is explicit, with one
thread, sequential execution and graph optimization disabled. No GPU provider fallback is selected.
A missing runtime gives an actionable error instead of fabricated vectors. Basic CLI/version/help
imports neither NumPy nor ONNX Runtime, even when installed.

There is no default model. For a completely local numerical smoke test from a checkout:

```bash
python -m pip install '.[onnx,onnx-dev]'
python -m tools.embedding_fixture --output workspace/embedding-oracle
# Uses original ReduceMean graph code, not pretrained weights or semantic inference.
takebraid embed /absolute/path/asset.json --stream 0 \
  --model workspace/embedding-oracle/model.json --every 25
```

The generated graph returns three RGB channel means; black gives a zero vector and unknown numeric
coverage. This recipe is an Apache-2.0 project oracle, not a learned model or a relevance benchmark.
It is generated outside Git. Supply a fresh destination; no existing model file is overwritten.

## Manifest contract

A schema 0.1 JSON object has exactly `provider`, `model`, `input` and `output` beside `schema_version`:

- `provider`: `onnx-cpu`.
- `model`: sibling `.onnx` basename, exact SHA-256, nonempty `id`, `revision`, `license`, `source` and
  `usage_permitted: true`. Source/license are operator declarations, not independently verified rights.
  The model must stay in the manifest directory and contain all initializers in a single file,
  at most 512 MiB. No URLs, path traversal or implicit external initializer files are loaded.
- `input`: tensor name, integer `width`/`height` in 16..512, `layout: NCHW`, `dtype: float32`,
  `color: RGB`, and three finite channel `mean`/`std` values. Means/stds have magnitude <=10;
  stds must be >=1e-6. Select `resize: stretch-area` for the existing FFmpeg path, or
  `resize: pillow-bicubic-short-edge-center-crop/1` plus integer `resize_short_edge` for the optional
  reference crop below. Other fields/resizers are rejected.
- `output`: tensor name, `dtype: float32`, integer `dimensions` in 1..4096.

Actual graph metadata must have exactly one static float32 `[1,3,H,W]` input and one static float32
`[1,D]` output with those names. Dynamic batch/geometry, token grids, text encoders, multi-output
models, external-data graphs and undeclared preprocessor contracts are unsupported.
Weights are read as bytes, hash-checked and passed to the runtime without a model filesystem path.
No custom-op library registration, Python model code or pickle loader is used. Models must still
be trusted: this is not a sandbox for arbitrary computational graphs.

With `stretch-area`, RGB decoding uses same-pass source PTS checks and FFmpeg area scaling to the declared
fixed dimensions. This **stretches the image**, including upscaling where required. It does not
silently apply CLIP/other model-specific crops, interpolation, channel order or normalization.
Use only an encoder compatible with the exact declared pipeline:

1. Decode unrotated source frames; verify every source PTS/geometry before sampling.
2. Scale to W×H using FFmpeg `area`, convert to RGB uint8.
3. Convert to float32, divide by 255, subtract channel means and divide by stds in RGB order.
4. Transpose to contiguous `[1,3,H,W]` and run the declared output on CPU.
5. Convert output to Python floats and L2-normalize in float64 arithmetic.

Unsupported media follows existing analysis restrictions (including HDR, rotation and unsupported
pixel formats). At most 1,000 samples and 256 MiB of decoded RGB are supported. `--every` is decoded
source-frame stride, not seconds or average FPS. Sparse inference still decodes the full source to
check its clock. PTS and rational time bases remain exact; vectors are floating-point measurements.
Model input dimensions and resizing do not alter source frame membership or source timestamps.

### Optional aspect-preserving bicubic crop

Explicitly install `takebraid[onnx,image-preprocessing]` to use the Pillow path. For the
[DINOv2 reference evaluation transform](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/data/transforms.py),
the input declaration is width/height 224, `resize: pillow-bicubic-short-edge-center-crop/1`,
`resize_short_edge: 256`, mean `[0.485,0.456,0.406]`, std `[0.229,0.224,0.225]`.
This is a preprocessing example, not a usable model manifest or a supplied checkpoint.

The short edge must be >= both crop edges and <=1024; no padding is inferred. Resize the original
RGB image with preserved aspect ratio (floor the long-edge dimension), Pillow `BICUBIC` and
`reducing_gap=None`, then crop at round-to-even half-offsets. Pillow's PIL bicubic path performs
antialiased resizing; this contract is not the torchvision tensor path. Upscaling is explicit.
Float32 normalization and ONNX execution then follow steps 3..5 above.

Every decoded source PTS/geometry is verified before stride selection. Only selected original RGB
frames enter the spool (256 MiB maximum, at most 1,000 samples); increasing `--every` reduces that
spool, not clock verification. Both source and resized frames are limited to 16 megapixels and
source edges to 3..16384. Over-budget inputs become explicit unknown coverage without inference.
Existing unsupported media/display-transform rules still apply. This does not normalize SAR.

Crop observations use recipe `local-onnx-image-embedding/2` and add the actual Pillow version to
runtime/cache identity; legacy stretch records remain recipe `/1`. Search validates both formats
without opening weights or importing Pillow. It rejects mixed crop/stretch or different Pillow
spaces. No prior cache is rewritten or silently promoted to the new recipe.

The [committed reference report](../tests/fixtures/embedding-preprocessing-reference.json) records
seven constructed images, byte-identical crop pixels and zero normalized tensor error against
torchvision 0.21.0 with torch 2.6.0, Pillow 13.0.0 and NumPy 2.3.5. Reproduce in a separate checkout
environment with those explicit versions (PyTorch/torchvision are not runtime dependencies):

```bash
PYTHONPATH=src python -m tools.check_embedding_preprocessing --output workspace/crop-reference.json
```

The destination must be new. Border-removal and negative/VFR fixtures exercise the actual decoder,
crop, ONNX oracle and saved-vector search. No learned weights are involved. See ADR 0015.

## Unknown coverage, failures and cache

Zero and nonfinite numerical outputs become explicit unknown rows with no vector. They are not
quality defects, normal-footage labels or weak positive scores. The report is `partial` if any
sampled row is unknown; globally unsupported input is `unknown` with no rows. Wrong output shapes
or runtime failures fail the attempt. Exit codes: 0 observed, 2 unknown/partial, 1 error, 130 cancelled.

`--timeout` bounds media processing. `--inference-timeout` requests cooperative per-frame termination
(default 30 seconds, maximum 300). It is not an operating-system hard deadline or a memory sandbox;
session construction/internal allocations are not bounded by that timer. Use trusted graphs.
The request uses the documented [RunOptions termination API](https://onnxruntime.ai/docs/api/python/api_summary.html#onnxruntime.RunOptions.terminate).

Recipe `local-onnx-image-embedding/1` keys include the model/manifest hash, full provenance and
preprocessing declarations, output dimensions, runtime/NumPy versions, runtime build/provider/options,
OS/machine information, media-tool builds, source/map hashes, sampling and deadlines. Model and
manifest are rehashed before cache reuse/publication. A cache hit still creates/validates the local
session and metadata; it skips media decode/inference. Checksummed terminal receipts and source/
vector validity are checked; edited cache outputs are rejected. `--force` preserves another attempt.

Numerical results can vary across hardware/runtime revisions. Stored outputs and their exact source
coordinates are the evidence; the implementation does not promise bitwise cross-platform inference.
A valid normalized vector does not prove useful semantics. Saved-vector
[cosine search](embedding-search.md) is now implemented without a model/runtime; actual
learned checkpoint/held-out duplicate-take evaluation remains subsequent work. `visual compare`
continues to accept only its grayscale descriptors, not these unrelated embedding spaces.

## Runtime initialization and privacy

The adapter sets `ORT_DISABLE_TELEMETRY=1` before importing the runtime, then calls its telemetry
disable API. A runtime already imported outside this adapter is rejected; start a fresh process.
The environment change is process-local and retained for that process. The key records this guard.
This is required because the [official privacy documentation](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md)
distinguishes initialization-time telemetry suppression from the later API call. The initial
implementation test exposed an initialization warning; API-only suppression was replaced before
publication. No request to download weights, upload frames or contact the manifest's source URL is
implemented. This is not a network trace certification for arbitrary third-party/native code.

The provider follows the official [Python API](https://onnxruntime.ai/docs/api/python/api_summary.html)
for bytes-loaded CPU sessions; the generated numerical oracle uses the official
[ONNX graph helpers](https://onnx.ai/onnx/api/helper.html). Dependency licenses and independently
supplied checkpoint rights are recorded separately in `THIRD_PARTY_NOTICES.md` and each manifest.

## Evidence and remaining work

Actual runtime tests verify RGB order/normalization against an analytical oracle, zero/nonfinite
unknowns, shape mismatches, weight tampering, external initializer rejection and cooperative
termination. FFmpeg tests cover caching/force/checksum rejection, CLI status, changed preprocessing
keys and signed/VFR coordinates against the independent source oracle. Core tests cover malformed
manifests, missing optional dependencies, numeric invariants, pre-import refusal and import isolation.
These are inference-contract tests, not learned-model accuracy.

Three existing CC0 original excerpts also have a local numerical run at
`workspace/embedding-pilot/runs-v2.json`: six sampled frames, using the synthetic channel-mean graph.
Grayscale inputs intentionally give equal RGB-channel directions; this demonstrates no semantic
separation. No natural duplicate/event labels, learned checkpoint or human accuracy claim follows.
The [validation summary](validation/local-onnx-summary.json) records hashes, settings/runtime and
numerical coverage for this run.
