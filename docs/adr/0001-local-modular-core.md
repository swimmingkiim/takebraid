# ADR 0001 — Local modular core, optional inference adapters

Status: accepted initial direction. Date: 2026-10-26.

## Context

Takebraid needs media correctness, replaceable video understanding, human overrides and reproducible
planning. The first use case is one user's local camera footage. GPU availability and model licenses
vary; there is no demonstrated need for multi-machine scheduling.

## Decision

Use one Python package/process initially. Keep domain values/planning pure and orchestrate side effects
in application use cases. FFmpeg, filesystem, model backends and export/UI are boundary adapters.
Use versioned project artifacts and saved model observations. Keep core installation free of model
frameworks. Default to local operation; remote inference is explicit and optional.

## Alternatives and consequences

- Microservices/queues provide isolation but add deployment and consistency work before a working
  pipeline exists. Revisit for measured multi-machine requirements.
- An all-in-one model agent reduces initial orchestration code but weakens temporal correctness,
  provenance and constraint enforcement. Restrict models to proposals checked by domain rules.
- A full desktop editor offers rich review but expands scope. Start CLI, then a small local review UI.
- Inspectable JSON is simple but can become slow to index; a project-local database can be introduced
  after measuring real project sizes, without changing editorial contracts.

This accepts some Python orchestration overhead and deliberate module boundaries. It does not call
for dependency injection frameworks, a generic plugin platform, or abstract interfaces with no use case.
