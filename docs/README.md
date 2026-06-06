# CloakBot Knowledge Base

This directory is the repository-local system of record for agents and humans.
`AGENTS.md` is only the table of contents. Start with the smallest document that
answers the task, then inspect the code paths it names.

## Map

- `ARCHITECTURE.md` - system layout, runtime surfaces, and dependency boundaries.
- `HACKATHON_WRITEUP.md` - the Gemma 4 Good Hackathon submission (May 2026);
  [published writeup on Kaggle](https://www.kaggle.com/competitions/gemma-4-good-hackathon/writeups/cloakbot-a-local-privacy-kernel-for-frontier-llms).
- `domains/privacy.md` - the privacy domain contract and current implementation.
- `design-docs/` - durable design principles and decisions.
- `product-specs/` - user-facing product behavior by area.
- `exec-plans/` - active/completed plans and the debt tracker.
- `references/` - external or long-form references summarized for local use.
- `demo/` - demo fixtures (e.g. `demo_onboarding_memo.md`) for the WebUI privacy demo (drag into the Composer).
- `SECURITY.md` - security and privacy invariants.

## Update Rules

- Keep docs close to code behavior. If a claim is not visible in code, mark it as
  planned or move it to the debt tracker.
- Prefer links to exact files over prose-only explanations.
- When adding a new subsystem, add one domain doc or update an existing one.
- When adding a new long-running task, create an execution plan instead of
  hiding context in chat.
- When removing or finishing planned work, update `exec-plans/tech-debt-tracker.md`.

## Harness Model

This layout follows the harness approach summarized in
`references/harness-engineering.md`: short entry instructions, progressive
disclosure through indexed docs, mechanically verifiable claims where possible,
and repeated cleanup of stale knowledge.
