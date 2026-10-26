# ADR 0004 — Manual source cuts, cumulative clocks and measurable MOV previews

Status: accepted initial implementation.

## Decision

Persist a one-source timeline containing exact source ranges and explicit rational output FPS/audio
intent. Compile cumulative video endpoints with nearest-half-up rounding, then derive audio sample
endpoints from the same frame clock. Validate against ready source frame maps at creation and execution.

Trim by decoded frame indices without input seeking. Render cuts separately, then join/normalize
clocks. Use MPEG-4 Part 2 + PCM MOV initially to avoid extra AAC encoder-delay ambiguity in decoded
audio-count checks. Decode the output to verify every video timestamp and audio sample continuity.
Preserve intermediate artifacts and reuse the checked stage mechanism.

## Consequences

Source decode repetition, intermediate disk use and a second lossy encoding are deliberate costs of
a small memory-bounded graph for arbitrarily reordered cuts. The preset is a preview, not a master.
Quantization may repeat/drop pictures or pad/trim audio by the documented grid error. MP4/AAC,
multi-source composition, lossless output and optimized seeking need separate validation/presets.
The runtime FFmpeg build must contain the required native codecs/filters; missing capability fails
with diagnostics rather than claiming successful output.
