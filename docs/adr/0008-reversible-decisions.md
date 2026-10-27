# ADR 0008 — Immutable decision snapshots and bound preview execution

Status: accepted initial implementation (TB-204).

## Decision

Create a complete source partition with keep/exclude/review/unknown states from validated temporal
interpretations. Candidate padding becomes review, missing evidence remains unknown, and other
frames are kept by the baseline inclusion policy. Keep is editing inclusion, not a quality verdict.
Only explicit user overrides can exclude. A chronological preview retains review/unknown footage.

Save additive UUID snapshots containing the frozen observation/interpretation references, cumulative
reasoned overrides, a checksummed parent and replayed intervals. Restore reapplies baseline states
within a range, recovering uncertainty as well as inclusion. It is not destructive undo; old records
remain usable as separate branches. Validate the history and recompute the selected snapshot before
using it. Bound history length rather than introducing a database or mutable global editing pointer.

A generated manual timeline references the exact decision snapshot/hash. Render orchestration
revalidates the snapshot, its evidence/history and exact included cuts before execution/cache reuse,
and checks dependency stability before certifying output. Decision previews use a separate recipe;
existing manual previews and temporal interpretation semantics/cache identities are unchanged.

## Consequences

The initial workflow is single-source and CLI-based. A user chooses a record explicitly; concurrent
edits can branch without overwriting each other. Restore means return to the frozen baseline, not
undo the immediately preceding edit or adopt a new analysis policy. Review/unknown states are never
silently discarded. Explicit all-source exclusion is representable, but no empty preview is rendered.

Records use inspectable local JSON, checksums and domain replay, not signed authorization or strong
adversarial isolation. No multi-file transaction, UI, multi-source assembly or automatic calibrated
exclusion is introduced. Real-footage precision/recall and editing usefulness remain TB-205/M4 work.
