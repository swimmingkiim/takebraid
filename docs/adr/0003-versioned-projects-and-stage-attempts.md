# ADR 0003 — Versioned registries, immutable attempts and checked cache pointers

Status: accepted initial implementation.

## Decision

Keep asset metadata immutable. A project registry stores current source locations and additive
editor annotations. Serialize registry writers with an exclusive local lock; preserve revision
snapshots before replacing the current pointer. Full source digests authorize relinking content
identity, not trusting an old locator, size or timestamp.

Stage identity is canonical versioned input data, separate from run identity. Each run writes a
unique attempt and terminal receipt. A successful derived cache pointer references an existing
completed receipt and a checked output digest. Loaders reconstruct domain validity independently
of saved status fields. Force reruns retain earlier artifacts; incomplete/failed attempts never
qualify as cache hits.

## Consequences

This supports inspectability and safe repeated local work without a database or distributed queue.
It accepts duplicate concurrent computation, orphan snapshots on interrupted publication, manual
stale-lock inspection and O(project size) registry validation. It does not implement a multi-file
transaction, automatic garbage collection or strong adversarial isolation. A database or worker
system should be introduced only when measured contention, size or scheduling needs justify it.
