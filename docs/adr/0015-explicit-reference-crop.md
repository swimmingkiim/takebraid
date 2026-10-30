# ADR 0015 — Optional reference crop before learned-checkpoint qualification

Status: implemented preprocessing slice; no pretrained checkpoint or semantic qualification.

## Decision

Keep the existing `stretch-area` inference recipe and saved records unchanged. Add an explicitly
selected Pillow bicubic short-edge resize and center-crop contract, with a declared short edge,
integer floor resize geometry and round-to-even crop offsets. Load Pillow only when that pipeline
is requested. Record its version and select inference recipe `local-onnx-image-embedding/2`.

Decode original RGB pixels, checking every decoded source PTS/geometry before selecting sampled
frames for the disk spool. Crop those samples before float32 normalization and ONNX invocation.
Bound source/resized image area and original sampled spool bytes; never first stretch to model
dimensions or silently reduce sampling to fit a budget.

## Evidence and consequences

Seven project-authored RGB patterns match torchvision's independent PIL evaluation transforms
byte-for-byte, including odd dimensions and upscaling. Normalized tensor maximum absolute error
is zero with the recorded versions. See the report and reproduction in `local-embeddings.md`.
Integration verifies border removal, negative/VFR timing, unsampled PTS checks, byte budgets and
saved-vector replay without Pillow/model imports. Strict space identity rejects old/new mixing.

This enables reference-shaped inputs, not a DINOv2 integration or measured duplicate-take quality.
Single-file export, original-versus-exported model parity, resource measurements and held-out
semantic evaluation remain separate requirements. Pillow's PIL path is not claimed equivalent
to torchvision's tensor interpolation path or every model's preprocessing.
