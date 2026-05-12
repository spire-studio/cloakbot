# Core Beliefs

## Agent Legibility First

Agents can only use context that is accessible in the repository or exposed by
standard tools. Important design context should live in Markdown, tests, schemas,
or executable checks instead of private chat history.

## Short Entrypoints, Deep References

`AGENTS.md` is a map. Detailed guidance belongs in indexed docs so agents can
load only the context needed for the task.

## Enforce Boundaries Centrally

Privacy, security, and dependency direction should be captured as tests, typed
contracts, or narrow runtime boundaries where feasible. Prose should explain the
rule, not be the only thing enforcing it.

## Prefer Boring, Inspectable Machinery

Choose simple code and stable dependencies that agents can inspect and reason
about. Avoid opaque behavior in the privacy path unless there is a clear benefit.

## Garbage Collect Continuously

When a bug, review comment, or stale doc reveals a recurring pattern, encode the
lesson in the relevant doc, test, or lint. Small cleanup beats large delayed
rewrites.
