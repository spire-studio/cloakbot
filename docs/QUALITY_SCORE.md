# Quality Score

This file tracks the current quality bar for agent work. Update it when the test
strategy or known gaps change.

## Current Grades

| Area | Grade | Notes |
| --- | --- | --- |
| Privacy core | B+ | Broad unit coverage exists for detectors, Vault, sanitizer, math, routing, protocol, and WebUI builders. Local model availability remains an integration variable. |
| Tool privacy | B | Interceptor and tests exist; approval and side-effect UX should keep receiving focused regression tests. |
| WebUI privacy panel | B | Privacy payload rendering and chat socket behavior have tests; automated screenshot regression is not currently planned. |
| Documentation harness | B | `docs/` now carries structured knowledge; no mechanical doc freshness check exists yet. |

## Required Checks By Change Type

- Docs-only: inspect changed docs and run a lightweight path check such as
  `find docs -name '*.md' -print`.
- Python privacy code: `uv run pytest -m "not integration" tests/privacy/` plus
  targeted tests for touched modules.
- Shared agent loop or runner: include `tests/agent/` and the relevant privacy
  runtime tests.
- WebUI privacy changes: run lint, tests, and build from `webui/`.
- Integration behavior that depends on vLLM: mark whether vLLM-backed tests were
  run or skipped.

## Known Gaps

See `exec-plans/tech-debt-tracker.md` for active debt. Do not duplicate long
roadmaps here; this file should stay focused on quality gates.
