# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1b1] - 2026-06-06

First **beta** of the privacy-kernel release: local PII detection, redaction, and
local restoration around a frontier LLM, rebased onto upstream nanobot@main.
Shipped as a pre-release (PEP 440 `0.2.1b1`) so the new trust-boundary subsystem
can be field-tested before `0.2.1` is declared stable; `pip` will not install it
without `--pre`. Tag once `main` carries this branch:
`git tag v0.2.1b1 && git push origin v0.2.1b1`.

### Added
- Privacy kernel rebased onto upstream nanobot: local detect → placeholder → 
  restore-locally pipeline wired through the agent loop, runner, and tool-I/O
  seams.
- Scoped, session-isolated Vaults; explicit egress policy with a provider gate;
  placeholder-stable context compaction; a streaming sanitizer with carry-over
  window.
- Visual/multimodal egress gate for image generation (fails closed on the prompt
  and on zero-region reference images).
- WebUI privacy surface: a Privacy settings tab, restoration highlight/hover/diff,
  and a localhost-gated privacy side-channel.
- `cloakbot onboard` step to configure the local privacy detector; the gateway now
  prints the WebUI URL and warns when `webui/dist` is unbuilt.

### Changed
- `config.privacy` is the only single source of truth for the detector connection;
  `.env`/`GEMMA_*` is no longer supported and the local LLM launcher scripts removed
  in favor of bring-your-own deployment plus docs.
- CI: force JavaScript GitHub Actions onto Node 24; pin Node and refresh deps.

### Fixed
- Never persist the raw `_agent_ui.privacy` blob to the WebUI transcript.
- cron/heartbeat dispatch runs ephemeral (no at-rest vault); the `/goal` at-rest
  sanitizer fails closed via the real detector.
- Never GPG-sign internal git memory-store commits.

### Tests
- Green non-integration suite; hermetic MCP probe socket tests; removed superseded
  pre-rebase test duplicates and stale xfails.

## [0.2.0] - 2026-06-03

Community and repository scaffolding.

### Added
- Code of Conduct, pull request and issue templates, `CODEOWNERS`, and a
  tag-driven release workflow.
- Label taxonomy as code (`.github/labels.yml`) with a sync workflow, plus
  path-based auto-labeling of PRs (`area: *`) via `.github/labeler.yml`.

### Changed
- CI: heavy optional-integration checks now run on a daily schedule and on manual
  dispatch instead of being gated on a `nightly` branch.

## [0.1.7] - 2026

Earlier release. See the Git history for details.

## [0.1.6] - 2026

Earlier release. See the Git history for details.

[0.2.1b1]: https://github.com/spire-studio/cloakbot/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/spire-studio/cloakbot/compare/v0.1.7...v0.2.0
[0.1.7]: https://github.com/spire-studio/cloakbot/releases/tag/v0.1.7
[0.1.6]: https://github.com/spire-studio/cloakbot/releases/tag/v0.1.6
