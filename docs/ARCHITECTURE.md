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
  `finalize_turn()` coordinate one privacy turn. `prepare_turn` accepts an
  optional `media=[...]` list so user-attached images flow through the visual
  pipeline *before* the context builder ever sees raw bytes.
- `cloakbot/privacy/core/detection/` - local PII detectors and JSON parsing.
  - `detector.py` is the user-input facade (general + digit detectors run
    concurrently).
  - `tool_detector.py` is the tool-output specialist. It runs the
    content-type sniffer, dispatches to the right chunker, runs `PiiDetector`
    per chunk under a semaphore with a per-chunk timeout, dedupes entities
    across chunks, and emits a `chunks_failed` signal that the interceptor
    uses to fail-closed on partial-detection cases.
  - `chunking/` — `Chunker` protocol plus four content-aware chunkers
    (`text`, `json_chunker`, `html`, `markdown`) and a conservative
    `sniffer` that picks among them.
- `cloakbot/privacy/core/sanitization/` - placeholder application, restoration,
  alias reuse, and public sanitization facade. `sanitize.py` now exposes
  `sanitize_tool_output_chunked` for tool outputs above the chunker threshold.
- `cloakbot/privacy/core/state/vault.py` - session-scoped placeholder and
  computation registry persisted under the privacy vault directory.
  `normalize_text` NFKC-normalises and strips combining marks so full-width
  and accented duplicates coalesce onto one placeholder.
- `cloakbot/privacy/core/math/` - remote snippet contract and local arithmetic
  execution.
- `cloakbot/privacy/runtime/tool_interceptor.py` - restores tool arguments for
  local execution, requests approval for non-local sensitive tool inputs, and
  sanitizes tool results, including file/document reads, before model reuse.
  It also persists sanitized read-file artifacts into the Vault and queues
  synthetic multimodal follow-up messages for the runner when a redacted image
  must be shown to the remote model. Routes large tool strings through
  `sanitize_tool_output_chunked`, short ones through the single-shot path.
  Skips detection on strings that are entirely placeholders (defence against
  nested-token corruption) and supports an opt-in
  `CLOAKBOT_APPROVAL_HIGH_SEVERITY_LOCAL` env var that extends the approval
  gate to LOCAL tools whose restored arguments contain `Severity.HIGH`
  entities.
- `cloakbot/privacy/visual_redaction.py` - local visual privacy pass for image
  blocks. Single `process_visual_blocks` helper shared by the tool-result and
  user-prompt entry points so policy cannot diverge. Uses the configured
  local vLLM/Gemma endpoint for sensitive-field identification and local
  OCR/Pillow for coordinate-based redaction. Renders a vault placeholder
  *inside* each redaction box so the downstream multimodal model can address
  redactions by name, with per-token rendering deduped so adjacent boxes
  sharing a placeholder don't cause the LLM to repeat the value in its reply.
  Emits a sibling region-map text block alongside each image for text-only
  models. Cross-modal recall bridge: text-side entities found by
  `PiiDetector` are forwarded as additional needles into the visual matcher,
  and any vault placeholder allocated by the visual phase is back-substituted
  into the OCR sanitized text via `smap.replace_known_originals`. Fails
  closed by default; configurable via `CLOAKBOT_VISUAL_FAIL_MODE`.
- `cloakbot/agent/tools/filesystem.py` - `read_file` tries the PDF text
  layer first (`fitz.get_text`) for digitally-issued PDFs; image-only PDFs
  fall back to the rasterise + visual-redaction path.
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
