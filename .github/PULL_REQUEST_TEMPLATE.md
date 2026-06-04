<!--
  Thanks for contributing to Cloakbot! Keep PRs small and focused —
  one logical change per PR is easier to review and easier to revert.
-->

## What does this PR do?

<!-- A short summary of the change and the motivation behind it. -->

## Related issues

<!-- e.g. "Closes #123". If there is no issue, briefly explain why this change is needed. -->

## How was this tested?

<!-- Commands you ran and what you observed. Paste relevant output if useful. -->

- [ ] `uv run ruff check cloakbot`
- [ ] `uv run pytest -m "not integration" tests/`
- [ ] WebUI changed → `cd webui && npm run lint && npm run test && npm run build`

## Checklist

- [ ] PR title follows [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`)
- [ ] One logical change; no unrelated refactors or formatting churn
- [ ] Docs updated if behavior changed (`docs/`, README, or `AGENTS.md`)

## Privacy & security boundary

<!-- Required if you touched cloakbot/privacy/** or cloakbot/security/**.
     These invariants come from AGENTS.md — they are the core trust contract. -->

- [ ] No raw sensitive value can reach the remote LLM path
- [ ] Placeholder ↔ raw mappings stay in the local session Vault and are restored locally
- [ ] Vault contents are never logged or written to remote-history payloads
- [ ] Tool privacy behavior is documented **as implemented**, not aspirationally
- [ ] N/A — this PR does not touch the privacy or security layer
