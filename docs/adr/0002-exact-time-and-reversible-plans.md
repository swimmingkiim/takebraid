# ADR 0002 — Exact time and reversible plans

Status: accepted. Date: 2026-10-26.

## Context

Footage can have VFR, fractional frame rates, nonzero/negative start PTS and independent audio clocks.
The system must let editors restore excluded material and revisit decisions after changing a brief.

## Decision

Represent source ranges with asset/stream identity, integer PTS, rational time base and `[in, out)`
semantics. Maintain source/proxy frame maps. Use an explicit output frame clock and audio sample clock.
Store observations, interpretations, decisions and render receipts separately. Exclusion never mutates
source media; user overrides create a revised plan, preserving prior evidence and plans.

## Alternatives and consequences

Float seconds are convenient for display but unsafe as the authoritative source coordinate. Average
FPS multiplication cannot locate VFR frames. Full event sourcing would track every internal operation
but adds complexity; simple versioned plan snapshots and small overrides suffice initially.

Arithmetic validation cannot prove valid media boundaries. Ingest must add source maps, the planner
must reject invalid references, and rendering must verify duration/alignment. More metadata and tests
are the deliberate cost of recoverable, inspectable editing.
