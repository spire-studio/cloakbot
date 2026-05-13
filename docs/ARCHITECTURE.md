# Architecture

CloakBot is a Python agent framework with a privacy layer wrapped around remote
LLM turns. The repository has three runnable surfaces:

- `cloakbot/` - Python CLI, gateway, channel integrations, providers, tools, and
  privacy runtime.
- `webui/` - React/Vite chat UI with privacy timeline and session snapshot
  surfaces.
- `bridge/` - TypeScript bridge package.

## Runtime Entry Points

- `cloakbot/cli/commands.py` constructs CLI, gateway, API, and WebUI commands.
- `cloakbot/agent/loop.py` receives messages, builds context, runs the provider
  and tool loop, applies privacy hooks, and saves sessions.
- `cloakbot/agent/runner.py` executes provider/tool iterations and calls the
  optional privacy interceptor around tool inputs and outputs.
- `cloakbot/channels/webui.py` bridges runtime events into WebUI payloads.

## Privacy Boundary

The main project-specific architecture is under `cloakbot/privacy/`.

```
user message
  -> cloakbot/privacy/hooks/pre_llm.py
  -> cloakbot/privacy/runtime/pipeline.py
  -> local detectors + Vault + intent routing
  -> remote LLM receives sanitized prompt
  -> cloakbot/privacy/hooks/post_llm.py
  -> local math execution, token restoration, report payloads
  -> user-visible response
```

Detailed behavior lives in `domains/privacy.md`.

## Important Modules

- `cloakbot/privacy/runtime/pipeline.py` - `PrivacyRuntime.prepare_turn()` and
  `finalize_turn()` coordinate one privacy turn.
- `cloakbot/privacy/core/detection/` - local PII detectors and JSON parsing.
- `cloakbot/privacy/core/sanitization/` - placeholder application, restoration,
  alias reuse, and public sanitization facade.
- `cloakbot/privacy/core/state/vault.py` - session-scoped placeholder and
  computation registry persisted under the privacy vault directory.
- `cloakbot/privacy/core/math/` - remote snippet contract and local arithmetic
  execution.
- `cloakbot/privacy/runtime/tool_interceptor.py` - restores tool arguments for
  local execution, requests approval for non-local sensitive tool inputs, and
  sanitizes tool results, including file/document reads, before model reuse.
- `cloakbot/privacy/protocol/` - strict event contracts, metrics, observability,
  and replay helpers.
- `cloakbot/privacy/webui/` - backend contracts and builders for WebUI privacy
  panels.

## Dependency Direction

Keep privacy dependencies predictable:

- Hooks call runtime.
- Runtime coordinates core, agents, protocol, and transparency.
- Core modules should not import WebUI modules.
- WebUI builders may read privacy contracts and snapshots, but should not mutate
  Vault state except through existing runtime/session paths.
- Tool privacy models are shared at the boundary between `agent/runner.py` and
  `privacy/runtime/tool_interceptor.py`.

When adding a new privacy capability, add the narrowest module at the layer that
owns the behavior and update `domains/privacy.md`.
