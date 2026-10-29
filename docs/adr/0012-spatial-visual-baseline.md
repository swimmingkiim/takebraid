# ADR 0012 — Exact spatial features as an explicit pre-model visual baseline

Status: accepted TB-301a baseline; learned embeddings and duplicate-take validation remain pending.

## Decision

Introduce a dependency-free 8x8 grayscale cell-mean descriptor and review-only cross-source sampled
frame matches. Reuse bounded PTS-verified decoding, source/map/tool provenance, immutable attempts
and receipt validation. Store all features/distances as exact rationals. Require explicit distance
and spatial-contrast tolerances; skip insufficient-contrast samples and mismatched source aspects.
Bound sample/pair work, report unknown inputs and deterministic truncation, and preserve sources.

Keep feature observations and candidate comparison artifacts separate from interpretations, user
editing decisions and timeline execution. The baseline is spatial intensity comparison, not a
semantic model. Do not call its distance a probability or promote matches to duplicate-take labels,
automatic exclusions or source deletion. No optional model is downloaded or imported.

## Consequences

This gives later image-embedding providers an inspectable measured baseline with exact media
coordinates and reproducible mechanics. It can run while independent M2 human review remains open;
neither milestone's accuracy gate is closed by this work. It cannot understand color, object/action
identity, complete events or editorial intent. Resizing/brightness/framing can change a match; very
different scenes can share cell means. Whole-take grouping and learned relevance remain TB-301 work.
Optimized implementations or changed descriptor semantics need new recipes and equivalent evidence.
