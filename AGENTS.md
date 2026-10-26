# Working on Takebraid

- Read `docs/architecture.md`, the relevant ADR, and `docs/roadmap.md` before changing boundaries.
- Keep `domain/` pure: no model frameworks, filesystem, subprocess, networking, or UI imports.
- Observations, policy decisions and timeline execution are separate concerns. A model proposes;
  validated code decides what can execute. Do not execute generated shell commands.
- Use integer source PTS and rational time bases. Intervals are `[in, out)`. Never recover VFR
  source positions by multiplying seconds by average FPS. Negative source PTS may be valid.
- Preserve source files. Exclusion means an editable timeline decision, never source deletion.
- Keep optional model/media dependencies out of the core install. Do not download weights during
  import, basic CLI use, or unit tests. Network use requires an explicit user-selected provider.
- Add evidence for behavior changes: media edge cases for time/rendering, labeled footage for
  selection/quality, and before/after measurements for performance. Do not claim unmeasured quality.
- Keep personal footage, credentials, caches and weights out of Git. Redistributable fixtures need
  a provenance/license entry. Record third-party code, checkpoint and dataset conditions separately.
- Update the roadmap and user-facing capability table when a feature actually ships. Do not add
  placeholder CLI commands that report success without performing their advertised work.
- Bump a stage's recipe version when analysis semantics change. Include all semantic inputs and
  tool/model revisions in its key; never trust saved status flags instead of domain validation.
- Run `python -m ruff check .`, `python -m ruff format --check .`, `python -m pytest`, and
  `python -m build` for changes affecting the package. Use a virtual environment.
- Keep architectural abstractions proportional to implemented use cases. Start in one process;
  introduce a separate service or plugin protocol only after a measured need.
