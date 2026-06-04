# Contributing to Cloakbot

We're glad you're here.

Cloakbot is built around a single conviction: privacy tooling should be trustworthy, transparent, and approachable. Every contribution — whether a bug fix, a new feature, or a documentation improvement — should move the project closer to that goal, not further from it.

## Maintainers

| Maintainer | Role |
|------------|------|
| [@laurieluo](https://github.com/laurieluo) | Project lead |

## Branching & workflow

We use a simple trunk-based (GitHub Flow) model. `main` is the only long-lived
branch — it is always releasable and protected (PR required, CI must pass).

**External contributors** work from a fork:

```bash
# Fork on GitHub first, then:
git clone git@github.com:<you>/cloakbot.git && cd cloakbot
git remote add upstream git@github.com:spire-studio/cloakbot.git
git fetch upstream
git switch -c feat/short-description upstream/main
```

**Maintainers** (with write access) branch directly in this repo — no fork.

Branch names use a type prefix: `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`,
or `test/`, e.g. `feat/telegram-rate-limit`.

- Keep PRs small. One logical change per PR is easier to review and easier to revert.
- If your change is exploratory or unfinished, open a draft PR and say so.
- Always branch off the latest `main`; rebase if your branch falls behind.

## Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/). The PR
title matters most — it becomes the squash-merge commit on `main` and feeds the
changelog:

```
feat(privacy): restore phone numbers in tool output
fix(telegram): handle empty allowFrom list
docs: clarify vault permissions
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `ci`.

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

## Pull request process

1. Push your branch and open a PR against `spire-studio/cloakbot:main`. Fill in
   the PR template.
2. CI must be green: the Python matrix (3.11–3.13), webui, bridge, and the Docker
   smoke test all run automatically. Run the local checks above first to avoid
   round-trips.
3. At least one maintainer approves. Changes under `cloakbot/privacy/` or
   `cloakbot/security/` require Code Owner review — these are the project's trust
   boundary.
4. A maintainer merges with **Squash and merge**, so each PR lands as a single
   Conventional-Commit on `main`. The branch is deleted automatically.

Before requesting review, confirm the privacy invariants in the PR template if
you touched the privacy or security layer.

## Releases

Releases use SemVer tags cut from `main`:

```bash
# Bump version in pyproject.toml first, then:
git tag v0.2.0 && git push origin v0.2.0
```

The `Release` workflow verifies the tag matches `pyproject.toml`, builds the
artifacts, and publishes a GitHub Release with generated notes. Record notable
changes in [`CHANGELOG.md`](CHANGELOG.md).

## Questions and Feedback

Open an [issue](https://github.com/spire-studio/cloakbot/issues) for bugs or feature discussions. For anything else, reach out directly:

- Laurie Luo (@laurieluo) — <me@laurie.pro>
