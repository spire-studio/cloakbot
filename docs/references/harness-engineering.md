# Harness Engineering Reference

Source: OpenAI, "Harness engineering: leveraging Codex in an agent-first world",
by Ryan Lopopolo (Member of the Technical Staff), published May 27, 2026.

URL: https://openai.com/index/harness-engineering/

## Local Takeaways

- Humans steer; agents execute. The engineering job shifts toward specifying
  intent, shaping environments, and building feedback loops.
- Repository-local knowledge must be the system of record because agents cannot
  depend on private conversations or external memory.
- `AGENTS.md` should be a short table of contents, not a monolithic handbook.
- Progressive disclosure matters: start agents with a stable map and point them
  toward deeper docs only when needed.
- Architecture and taste should be enforced through boundaries, tests, lints, or
  typed contracts where possible.
- Cleanup should be continuous. Stale docs and uneven patterns compound quickly
  when agents copy what already exists.

## Applied In This Repo

- Root `AGENTS.md` now points to `docs/` instead of carrying all guidance inline.
- Privacy domain knowledge is split into `docs/domains/privacy.md`.
- Execution plans and debt tracking live under `docs/exec-plans/`.
- Security expectations are captured in a discoverable document
  (`docs/SECURITY.md`). Quality and reliability expectations are not yet split
  into their own documents.

## Not Adopted Yet

- There is no custom docs linter or freshness checker.
- There is no recurring doc-gardening automation.
- Architecture boundaries are documented but not fully enforced by structural
  tests.
