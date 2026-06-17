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
- `cloakbot/channels/websocket.py` and `cloakbot/channels/websocket_privacy.py`
  (the `PrivacyWebSocketChannel` subclass) bridge runtime events into WebUI
  payloads; `cloakbot/webui/ws_http.py` serves the WebSocket/HTTP routes.

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
  pipeline *before* the context builder ever sees raw bytes. Per-turn
  observability events are emitted through a `_TurnObservability` helper whose
  `span()` context manager brackets each stage's started/succeeded/failed triple.
- `cloakbot/privacy/runtime/attachments.py` - pure, ctx-free decoding of
  `media=[...]` references into image `image_url` blocks and decoded text-document
  tuples (extracted from `pipeline.py`). Logging only ever prints a redacted
  `media_fingerprint`, never the raw reference.
- `cloakbot/privacy/core/placeholders.py` - the single source of truth for the
  `<<TAG_N>>` placeholder grammar (the trust-boundary token format): the
  compiled patterns (`PLACEHOLDER_RE`, `TOKEN_RE`, `PLACEHOLDER_TAG_RE`,
  `INTERNAL_TOKEN_RE`), token helpers (`is_placeholder`, `placeholder_tag`,
  `placeholder_inner`, `entity_type_from_placeholder`), and the token-aware
  span helpers (`protected_spans`, `find_unprotected_positions`) shared by the
  sanitizer and vault. Every module that matches/extracts/filters tokens imports
  from here so the grammar cannot drift between the mint path and an egress path.
- `cloakbot/privacy/core/detection/` - local PII detectors built on PydanticAI.
  - `detector_model.py` binds the shared local detector endpoint to a PydanticAI
    model, reusing the `config.privacy` `AsyncOpenAI` client (so the endpoint
    stays defined in `providers/detector.py`). Detectors use `NativeOutput`: the
    local endpoint advertises JSON-Schema structured output (vLLM guided
    decoding / Ollama schema format), so PydanticAI constrains decoding to the
    entity schema. The hand-tuned detector prompts stay byte-for-byte — the
    schema travels in the API `response_format`, not the prompt.
  - `detector.py` is the user-input facade (general + digit detectors run
    concurrently). `general_detector.py` / `digit_detector.py` are PydanticAI
    agents whose typed `output_type` replaces hand-rolled JSON parsing; an
    `output_validator` enforces the privacy-bearing filters (exact-substring,
    internal-token, de-dup) as deterministic backstops.
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
- `cloakbot/privacy/core/state/` - the session-scoped placeholder/computation
  vault, split into a clean dependency chain behind a facade:
  - `registry.py` - the in-memory data model (`_SessionMap`, `VaultEntity`,
    `VaultComputation`). `normalize_text` NFKC-normalises and strips combining
    marks so full-width and accented duplicates coalesce onto one placeholder.
  - `vault_store.py` - workspace-scoped disk + artifact serialization (atomic
    map persistence, tool-artifact bytes). No scope/cache awareness.
  - `scope.py` - Cap B scope routing (`VaultScope`, `use_ephemeral_scope`,
    `route_fixed_key_through_active_run`), the live in-memory caches, and the
    `get_map` / `save_map` access facade.
  - `vault.py` - the public facade everything imports from; composes the three
    layers and re-exports the cohesive vault API.
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
  redactions by name. Every matching box is labelled (the earlier
  one-box-per-token-family overlay was dropped); placeholder de-duplication
  now happens in the sibling region-map text block, not in the image.
  Emits a sibling region-map text block alongside each image for text-only
  models. Cross-modal recall bridge: text-side entities found by
  `PiiDetector` are forwarded as additional needles into the visual matcher,
  and any vault placeholder allocated by the visual phase is back-substituted
  into the OCR sanitized text via `smap.replace_known_originals`. Fails
  closed by default; configurable via `CLOAKBOT_VISUAL_FAIL_MODE`.
- `cloakbot/agent/tools/filesystem.py` - `read_file` tries the PDF text
  layer first (`fitz.get_text`) for digitally-issued PDFs; image-only PDFs
  fall back to the rasterise + visual-redaction path.
- `cloakbot/privacy/protocol/` - the turn observability event protocol.
  `contracts.py` holds the live event schema (`EventRecord` + the
  `EventType`/`PrivacyStage`/`ProtocolStatus` enums); `observability.py` mints and
  sinks events; `metrics.py`/`replay.py` read them back; `timing.py` is the shared
  `elapsed_ms` helper. (The earlier aspirational, unused contract schema was
  removed.)
- `cloakbot/privacy/webui/` - backend contracts and builders for WebUI privacy
  panels. `side_channel.py` assembles the privacy side-channel payload and
  exposes `project_payload_for_egress()`, which returns a redacted projection
  for non-localhost connections. The localhost gate that decides full-vs-redacted
  is enforced in `cloakbot/webui/privacy_routes.py` — the WebSocket channel can
  bind `0.0.0.0`, so this gate, not the bind address, is the trust boundary.
- `webui/src/overlays/privacy/` - the React privacy overlay (timeline, inspector,
  Local↔Remote diff). This replaced the earlier `webui/src/features/privacy`
  layout.

## Dependency Direction

Keep privacy dependencies predictable:

- Hooks call runtime.
- Runtime coordinates core, agents, protocol, and transparency.
- `core/placeholders.py` is the lowest layer (depends on nothing privacy-internal);
  the sanitizer, vault registry, detectors, math, and egress gate all import the
  token grammar from it. Inside `core/state/`, the dependency chain is
  `registry → vault_store → scope → vault` (the facade); never import a
  higher link from a lower one.
- Core modules should not import WebUI modules.
- WebUI builders may read privacy contracts and snapshots, but should not mutate
  Vault state except through existing runtime/session paths.
- Tool privacy models are shared at the boundary between `agent/runner.py` and
  `privacy/runtime/tool_interceptor.py`.

When adding a new privacy capability, add the narrowest module at the layer that
owns the behavior and update `domains/privacy.md`.
