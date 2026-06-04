# Agent Harness

This file is the entry point, not the manual. Keep it short. Repository knowledge
lives in `docs/`, and code behavior is the final source of truth when docs drift.

## Operating Contract

- State assumptions before coding. If a requirement has multiple plausible
  meanings, name the alternatives and ask only when guessing would be risky.
- Prefer the smallest change that solves the stated problem. No speculative
  features, broad refactors, or new abstraction unless the existing code shape
  requires it.
- Touch only files that trace directly to the request. Do not clean up unrelated
  code, formatting, or user work already present in the tree.
- Turn each task into verifiable success criteria, then loop until checked.
- If docs and code disagree, inspect code, update the relevant doc, and mention
  the mismatch in the final response.

## Where To Look

Start here:

- `docs/README.md` - knowledge base map and update rules.
- `docs/design-docs/core-beliefs.md` - operating principles for agent-readable
  development (agent legibility, short entrypoints, continuous cleanup).
- `docs/ARCHITECTURE.md` - runnable surfaces, module boundaries, dependency map.
- `docs/domains/privacy.md` - privacy pipeline, trust boundary, current feature
  boundaries. Read this before changing anything under `cloakbot/privacy/`.
- `docs/SECURITY.md` - security invariants and privacy-sensitive handling.
- `docs/HACKATHON_WRITEUP.md` - hackathon submission narrative and the
  evidence stack (A1/A2/A3 leak evals); useful context for the privacy layer.
- `docs/exec-plans/README.md` - when to create an execution plan.
- `docs/exec-plans/tech-debt-tracker.md` - known gaps; update when you create or
  retire debt.
- `docs/references/harness-engineering.md` - local summary of the harness model
  used to organize this repo.

## Privacy First

The project-specific core is `cloakbot/privacy/`. For privacy work, read
`docs/domains/privacy.md` and the directly involved code before editing.

Hard boundaries:

- Raw sensitive values must not be sent to the remote LLM path.
- Placeholder mappings live in the session Vault and are restored locally.
- User-visible output may be restored locally; inspect sanitized prompts and
  remote-history payloads when checking the remote trust boundary.
- Math turns may ask the remote model for structure, but local code executes
  arithmetic against Vault values.
- Tool privacy behavior must be described as implemented, not aspirational.

## Verification

Use the narrowest meaningful checks first:

- Python docs-only sanity: `find docs -name '*.md' -print`
- Python lint touched code: `uv run ruff check <paths>`
- Privacy tests: `uv run pytest -m "not integration" tests/privacy/`
- Full non-integration suite: `uv run pytest -m "not integration" tests/`
- WebUI changes: from `webui/`, run `npm run lint`, `npm run test`, and
  `npm run build` as appropriate.

Integration tests that require vLLM should be called out explicitly if not run.

## Documentation Rules

- `AGENTS.md` points to durable docs; do not grow it into a long handbook.
- Add new domain knowledge under `docs/` with an index entry.
- Capture complex, multi-step work as an execution plan under
  `docs/exec-plans/active/`; move it to `completed/` when done.
- Keep README user-facing. Put engineering detail in `docs/`.
