# ADR 0014 — Runtime-free cosine retrieval from checked saved embeddings

Status: accepted TB-301c numerical retrieval slice; learned semantics and take grouping pending.

## Decision

Separate embedding generation from saved-vector search. Validate model specification metadata
without opening weights, reconstruct the source-clock context, check terminal receipts and numerical
coverage, and compare only strictly compatible model/preprocessing/runtime/media spaces. This
allows archived model outputs to be replayed by a core-only installation with source/media tools.
The existing inference recipe and output semantics are unchanged by sharing their validation code.

Provide bounded exact pair enumeration over saved floating unit vectors, explicit cosine thresholds,
unknown-pair accounting, deterministic ranking/truncation and immutable search-stage provenance.
Include the Python/platform math environment in the new search recipe's key. Do not mix grayscale
spatial descriptors with model embeddings or treat a score as an editorial confidence probability.

## Consequences

No provider initialization, optional numeric library, checkpoint lookup, remote index or service is
needed for this implemented use case. Source/project validation remains required. Strict full-space
identity can reject harmless filename/provenance aliases; accepting looser compatibility requires
future evidence. Scoring remains a sampled-frame proposal, not a full duplicate-take interpretation.
Source timing stays exact while similarity is floating-point. Human quality/duplicate/event gates,
pretrained checkpoint qualification and temporal take grouping remain open.
