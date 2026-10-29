# ADR 0013 — Explicit local CPU encoder and declared preprocessing before semantic claims

Status: accepted TB-301b inference adapter; learned checkpoint and semantic validation pending.

## Decision

Add one concrete optional ONNX CPU image-encoder adapter, loaded only on explicit `embed --model`.
Require a single-file local checkpoint hash, revision/license/use declaration, static tensor shapes
and a strict RGB stretch-area/mean/std NCHW float32 contract. No registry, automatic model selection,
network downloader, custom Python model code, external initializer resolution or mandatory runtime
is introduced. Keep model libraries out of domain and basic CLI imports.

Reuse bounded source-PTS-verified decoding, now with RGB alongside the unchanged gray path. Cache
floating unit vectors with exact source coordinates and all model/preprocessing/runtime provenance.
Retain zero/nonfinite outputs as unknown, reject shape/receipt/source mismatches, and preserve
immutable stage history. A per-frame cooperative runtime deadline supplements the media timeout;
it does not sandbox untrusted graphs or bound initialization/internal allocation.

Suppress runtime telemetry before import, and reject an already externally imported runtime because
an API call after initialization cannot undo initialization events. Record the process-local guard
and call the disable API as well. Do not claim a network-trace guarantee for native dependencies.

## Consequences

A caller with a permitted compatible model can execute and cache actual local inference. The project
ships no pretrained checkpoint or unsupported relevance guarantee. Synthetic generated ONNX graphs
verify numerical contracts in a separate optional CI job; they are not semantic models. Default
CI/core installs work without NumPy, ONNX Runtime, graph-generation tools or media downloads.
Different embedding spaces cannot be mixed with grayscale visual descriptors. Learned checkpoint
qualification, cosine retrieval, duplicate-take labels and M2/M3 study gates remain open.
