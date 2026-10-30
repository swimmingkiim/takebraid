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

## Efficient development and continuity

- Locate relevant files with `rg --files` and `rg -n`; read only the needed sections.
  Consult original sources when summaries are insufficient; avoid rereading whole logs or docs.
- Split complex work into verifiable features or bug fixes with expected behavior and completion
  criteria. Reuse existing code and tools; avoid unrelated refactors and unnecessary process.
- Match verification to impact, retain the package checks above, and inspect actual UI when
  applicable. Report skipped or unavailable checks; never skip necessary checks to save tokens.
- After two failures with the same approach, record the evidence and change the approach.
- On long-task interruption or handoff, update the existing task record with completed/pending
  work, verification, unresolved issues, next steps, and relevant files/commits. Avoid duplicating
  explanations across documents. Keep final reports focused on results, checks, and remaining issues.

## Project entry points

- Structure: `src/takebraid/` contains the package, `tests/` contains tests, and `tools/` contains
  validation utilities. Keep the existing domain boundaries described above.
- Setup (from this directory): `python3 -m venv .venv`, `source .venv/bin/activate`, then
  `python -m pip install -e ".[dev]"` (Python 3.11+).
- CLI checks: `takebraid --version` and `takebraid doctor`; media processing needs external
  FFmpeg and ffprobe. Basic package tests need neither models nor media tools.
- Package verification: the Ruff, pytest, and build commands above are the required commands.
  Media validation when relevant: `python -m tools.media_validation --output workspace/media-validation`.
- References: `README.md`, `README.ko.md`, `pyproject.toml`, `.github/workflows/ci.yml`,
  `docs/architecture.md`, relevant `docs/adr/`, `docs/roadmap.md`, and `docs/media-validation.md`.
- Preserve existing guidance when updating instructions. Instruction-only work must not change
  application behavior or advance feature completion claims in the roadmap.
