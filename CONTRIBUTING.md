# Contributing to Cloakbot

We're glad you're here.

Cloakbot is built around a single conviction: privacy tooling should be trustworthy, transparent, and approachable. Every contribution — whether a bug fix, a new feature, or a documentation improvement — should move the project closer to that goal, not further from it.

## Maintainers

| Maintainer | Role |
|------------|------|
| [@laurieluo](https://github.com/laurieluo) | Project lead |

## Branching

All contributions target `main`. We keep a single stable branch and expect PRs to be focused and self-contained before merging.

- Keep PRs small. One logical change per PR is easier to review and easier to revert.
- If your change is exploratory or unfinished, open a draft PR and say so.

## Development Setup

```bash
git clone https://github.com/spire-studio/cloakbot.git
cd cloakbot

uv sync

# Run tests
pytest

# Lint and format
ruff check cloakbot/
ruff format cloakbot/
```

## Code Guidelines

We value code that is easy to read six months from now, by someone who wasn't in the original discussion.

- Solve the actual problem, not a generalized version of it
- New abstractions should visibly reduce complexity, not relocate it
- Avoid touching unrelated code in the same PR
- If something is surprising, leave a comment explaining why

**Tooling:**
- Python 3.11+
- Line length: 100 characters (`ruff`)
- Linting rules: E, F, I, N, W (E501 ignored)
- Async: `asyncio` throughout; tests run with `asyncio_mode = "auto"`

## Questions and Feedback

Open an [issue](https://github.com/spire-studio/cloakbot/issues) for bugs or feature discussions. For anything else, reach out directly:

- Laurie Luo (@laurieluo) — <me@laurie.pro>
