# Contributing

Takebraid is in bootstrap. Pick a bounded roadmap task and describe its inputs, outputs and
acceptance evidence before implementing it. For a substantial boundary change, propose a short
ADR under `docs/adr/`; small fixes do not need one.

## Setup and checks

Use Python 3.11+ and a virtual environment, then `python -m pip install -e ".[dev]"`.
Top-level development tools and the build backend are pinned in `pyproject.toml`. Transitive
dependencies are not yet fully locked; release/evaluation manifests must record the resolved set.

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
python -m build
```

CI runs unit tests on Linux, macOS and Windows with the minimum and latest tested Python versions.
Media integration tests will be added in M1 with explicitly installed FFmpeg and licensed fixtures.
Model evaluations belong in a separate opt-in suite, not the basic unit-test job.

## Evidence and review

- Time/render changes need CFR/VFR, nonzero/negative PTS and audio alignment evidence as applicable.
- Quality/selection changes need labeled examples, false exclusions and comparisons to a baseline.
- Distinguish measured output, model inference and editorial policy in code and documentation.
- Keep new dependencies optional when their feature is optional. Document the exact model revision.
- Include provenance and redistribution permission with every committed media fixture.
- Do not contribute private media or API keys. Do not attach user footage to public issues without
  the owner's explicit permission.
- Keep reviews respectful and technical; explain the user-visible effect and known limits.

Contributions are made under the project's Apache-2.0 license. Contributors must have the right
to submit their work. Code, model weights and data licenses are reviewed independently; a public
download is not sufficient evidence of redistribution permission.
