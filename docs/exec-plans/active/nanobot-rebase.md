# Nanobot Rebase + Privacy Overlay (Full Parity)

## Goal

Re-fork the core from upstream `HKUDS/nanobot@main` (v0.2.1+ "Workbench") to reach
full feature parity, re-express the privacy kernel as a clean **additive overlay**
(one `PrivacyHook` + one tool-IO interceptor + one privacy WebSocket subclass +
one frontend `overlays/privacy/`), and rework the privacy pipeline internals
(streaming sanitizer, scoped vaults, egress policy, stable compaction, multimodal
egress, webui side-channel) so the previously-gated features become safe to ship.

## Status

- Created: 2026-06-04. State: **W0 + W1b done; non-integration suite GREEN** on branch
  `rebase/v0.2.1` (`main` untouched; snapshot tag `pre-rebase-snapshot`; `upstream` remote).
  Suite: **4077 passed, 17 xfailed (documented), 0 unexpected failures** (`-m "not integration"`).
  - W0 done: tree lay-down `58dba2b` (upstream `nanobot@87bd564`, renamed, attribution
    URLs preserved, Workbench `webui/` adopted, privacy package restored). Deps merged
    `39cb6e8` (upstream runtime deps + our privacy deps + cloakbot metadata); `uv sync`
    clean. **`import cloakbot` + CLI + new subsystems (`apps`/`pairing`/`autocompact`/
    `fallback_provider`/`signal`) all green at upstream parity.**
  - W1a done `f994da6`: privacy package imports clean on the rebased core — only 1 of 4
    core helpers was missing (`get_privacy_vault_dir`, re-homed into `vault.py`;
    `ToolCallRequest`/`detect_image_mime`/`stringify_text_blocks` already exist upstream).
    **103 privacy-core + sanitizer tests pass** (detection/sanitization/vault/math intact).
  - W1b runner seam done `04d8509` [seam:4+5]: `ToolPrivacyInterceptorProtocol` +
    `AgentRunSpec.tool_privacy_interceptor` + `_tool_privacy_class` + `_run_tool` brackets
    (restore tool args locally before exec; sanitize tool output before model reuse).
    Verified neutral — `tests/agent/test_runner.py` identical 10-fail/15-pass with & without
    the seam.
  - **W1b loop seam DONE** `dac638b`,`2d6ab41` — **privacy enforcement is ON for the live
    text path.** `set_vault_workspace` in `__init__`; `TurnContext.privacy_ctx` (aliased
    import, no rename needed); `_state_build` sanitizes the user turn before prompt+persist
    and forces non-streaming when sanitized (no mid-stream placeholder leak); `_state_run`
    threads `ToolPrivacyInterceptor`; `_run_agent_loop`+`AgentRunSpec` carry it;
    `_state_respond` restores before the user sees output. Runner follow-up
    (`take_follow_up_messages`) wired. **Verified by an e2e leak test**
    (`tests/agent/test_loop_privacy_seam.py`): the real `AgentLoop` payload to the provider
    carries `<<PERSON_1>>`, never the raw value. Privacy suite **209 passed / 2 failed**
    (the 2 are `test_pdf_text_layer.py` → W3).
    - Refined so the seam is transparent on clean turns (`7195e3d`): only mutates the turn
      when the detector actually redacts; the transparency report is no longer appended to
      content (moves to the WebUI side-channel, W2). Known gaps until later waves: media/visual
      privacy passes through unchanged (W3); streaming forced off for sanitized turns (UX
      upgrade = buffering `PrivacyHook`, later); tool-approval flow (W2).
  - **W0-tail done** (`7195e3d`,`840c9dd`,`aacd8d9`): autouse fixture makes the local detector
    available-but-empty so privacy is on-but-inert in tests; fixed `make_provider`
    (`estimate_prompt_tokens` moved off `LLMProvider` upstream); neutralized the dev's git
    commit-signing for dulwich `GitStore` tests; renamed the misnamed facade
    `cloakbot/nanobot.py`→`cloakbot.py` (+`Cloakbot` alias/export). Remaining failures are
    xfailed/ignored with reasons: 12 stale fork tests (pre-rebase runner/facade internals),
    2 W3 (pdf/visual), 3 sandbox-env (network/socket), 2 removed modules (heartbeat fork
    feature dropped; webui channel → W2).
  - Next: W1 finish (Cap B scoped vaults, Cap C egress policy) → W2 (adopt Workbench webui +
    privacy overlay + side-channel + **localhost gate** + re-home webui channel) → W3 (streaming
    sanitizer + visual read_file + exec_session/apply_patch) → W4–W7. Also: restore the
    `heartbeat` fork feature if wanted; re-apply visual `read_file` (un-xfail pdf tests).
  - A1/A2/A3 leak-evals (need local vLLM) not yet run — schedule once W1 finishes.
- Upstream baseline: nanobot `v0.2.1` (2026-06-01), tracked at `main`.
- Fork point: nanobot `v0.1.x`. Drift ≈ one minor release + ongoing fixes.
- Companion analysis (not checked in): two design workflows produced the seam map,
  capability spec, WebUI plan, and an adversarial critique that found the blocking
  side-channel invariant below. Their conclusions are inlined here so this doc
  stands alone.

## Assumptions

- The privacy package `cloakbot/privacy/**` (≈48 modules) is self-contained and
  imports nothing core-mutating; it survives the rebase nearly verbatim. Verified
  by import audit; re-verify with the CI grep gate (see Validation).
- Upstream has **zero** privacy concept (`privacy_snapshot` / `tool_approval` →
  0 hits in the upstream tree); everything privacy is net-new additive, never a
  rename to reconcile.
- Upstream already exposes the additive seams we need: `AgentHook`/`CompositeHook`
  lifecycle, `AgentRunSpec.hook` wiring, and the channel-agnostic UI side-channel
  `OUTBOUND_META_AGENT_UI = "_agent_ui"` metadata passthrough in
  `channels/websocket.py`.
- CloakBot's current frontend (`webui/src/features/**`) is a skeleton; there is
  little bespoke UI to preserve. The asset to keep is the **data contract**
  (`cloakbot/privacy/webui/contracts.py`), not the transport.
- We adopt upstream's pinned webui stack (React 18.3 / Tailwind 3.4 / Vite 5.4 /
  Vitest 2.1 / TS 5.7 / i18next), not the current fork's newer stack.

## Decisions

- 2026-06-04: **Strategy = rebase-on-upstream.** Clean re-fork of the upstream tree
  + privacy as a vendored overlay package + a thin, labeled core patch set; add a
  `git` `upstream` remote for cheap future syncs. Rejected git-subtree (forces a
  double import root) and perpetual full-tree merge (re-conflicts the same 3 files
  every sync).
- 2026-06-04: **WebUI = adopt upstream Workbench wholesale, privacy as a frontend
  overlay** fed by a backend side-channel riding `_agent_ui.privacy` + additive
  `privacy_trace` events. Delete the bespoke SPA; port the privacy components into
  `webui/src/overlays/privacy/`.
- 2026-06-04 (D6): **Rename the upstream package root `nanobot` → `cloakbot`** at
  re-fork time (one scripted, replayable commit) so the 48 privacy modules' imports
  and all `tests/**` resolve unchanged. (Maintainer: confirmed.)
- 2026-06-04 (D1): **CLI-Anything / arbitrary user-registered CLI apps default to
  `EXTERNAL` + human approval, plus an explicit per-app allow-list.** No auto-install
  from model output; egress logged. (Maintainer: confirmed.)
- 2026-06-04 (D7): **Do not upstream the two structural seams to nanobot yet.**
  Carry `before_turn(user_message)` and `AgentRunSpec.tool_privacy_interceptor` as
  the local patch set; revisit later. (Maintainer: deferred.)

## Blocking Invariant — Side-Channel localhost gate (must not regress)

The privacy side-channel ships **raw** PII to the client by design (the Privacy
Inspector's purpose is showing placeholder ↔ real value). Verified raw-bearing
fields:

- `SessionEntityData.{canonical,aliases,value}` — `cloakbot/privacy/transparency/report.py:37-39`
- `WebUIToolApproval.restored_arguments` — `cloakbot/privacy/webui/contracts.py:70`
- `WebUIUserAttachment.original_data_url` — `contracts.py:92` (un-redacted image)
- `WebUIUserDocument.original_text` — `contracts.py:114` (un-sanitized document)
- `RestoredTokenAnnotation.{text,value,canonical,formula}` — `core/sanitization/restorer.py`

This is safe **today only because** `cloakbot/channels/webui.py:84` hard-binds
`host = "127.0.0.1"` (the `contracts.py` docstring states the design depends on the
"data never leaves localhost" boundary). Upstream `channels/websocket.py` supports
`host=0.0.0.0`/all-interfaces with token auth as a **first-class, parity-goal**
feature. Re-homing the side-channel onto it without a gate would egress the
cleartext vault to any authenticated remote client — strictly worse than the
remote-LLM boundary this project exists to protect.

**Required (blocking acceptance test in W2, Capability F):**

- Emit the full `WebUIPrivacyPayload` (and the `GET /api/sessions/{key}/privacy`
  route, and `ToolApprovalPrompt` authorization) **only to `_is_localhost(connection)`
  connections** (upstream provides this per-connection check).
- Non-localhost connections receive a **redacted projection**: placeholders +
  entity types/severities/counts only; strip `value`, `canonical`, `aliases`,
  `originalDataUrl`, `originalText`, `restoredArguments`, `RestoredTokenAnnotation.text/value`.
- Test: *"a non-localhost client receives zero raw entity values, original images,
  original documents, or restored arguments."*

## Repo Strategy & Layout

```
cloakbot/                      # = upstream tree, package root renamed nanobot -> cloakbot
  agent/{loop,runner,hook,...}.py   # upstream + the 3 labeled structural seam patches
  channels/websocket.py             # upstream + PrivacyWebSocketChannel subclass
  webui/{ws_http,transcript,...}.py # upstream gateway + additive privacy routes
  privacy/**                        # OUR package, dropped in unchanged (~48 modules)
  tool_privacy.py                   # OUR ToolPrivacyClass enum, unchanged
webui/                         # = upstream Workbench webui on ITS pinned stack
  src/overlays/privacy/**           # NEW frontend privacy overlay (ports of local components)
docs/REBASE/                   # NEW patch-set log + upstream sync runbook
```

Future syncs: `git fetch upstream`, re-fork tree, replay the labeled `[seam:N]`
commit series, resolve only seams whose host method changed shape. A CI grep gate
asserts no privacy import leaks into non-seam core files.

## Seam Map

Re-apply in this order. Effort S=one-liner, M=moderate, L=structural.
Mechanism: *Extension* = additive hook/field/method (preferred); *Fork* = surgical
insert into a reworked upstream method.

| # | Seam (local → upstream) | Mechanism | Effort | Risk | Shape changed upstream? |
|---|---|---|---|---|---|
| 1 | `agent/hook.py` ← upstream `AgentHook`/`CompositeHook` | Take upstream superset | S | Low | API-compat superset |
| 4 | `AgentRunSpec.tool_privacy_interceptor` field | Extension | S | Low | Field absent upstream |
| 6 | `set_vault_workspace(workspace)` bind in loop `__init__` | Fork (1 line) | S | Low | `__init__` grew, insert trivial |
| 8 | `session/manager.py` `get_display_history` | Extension (additive method) | S | Low | Additive |
| 10 | SDK facade `cloakbot.py` `_extra_hooks` swap | Take upstream | S | Low | API-compat |
| 12 | `command/*` builtin commands | Pure rebase | S | Low | Clean |
| 11 | `cli/commands.py` provider wiring (+egress gate) | Pure rebase + Cap C | S | Low | Analogous factory |
| 9 | tool class tags → **EgressPolicy registry** | Replace (Cap C) | M | Med | Tool set grew — must classify new tools |
| 3 | interceptor wiring in loop `_state_run` `AgentRunSpec(...)` | Extension | M | Med | No privacy arg upstream |
| **2** | **turn sanitize/restore → `PrivacyHook` + `before_turn` bracket** | **Fork `_state_build`/`_state_respond`** | **L** | **High** | **State-machine rewrite — re-implement, do not port** |
| **5** | **tool-IO interception → `_run_tool` prepare/sanitize bracket** | **Extension + minimal bracket** | **L** | **High** | `_run_tool` enlarged (`_classify_violation`, file-edit trackers) |
| **7** | **`channels/webui.py` → `channels/websocket.py` + `webui/ws_http.py`** | **Discard bespoke server; re-home onto `_agent_ui` + additive routes** | **L** | **High** | Transport replaced (FastAPI → raw `websockets`) |
| 13 | `tools/filesystem.py` visual handoff | no seam (rides payload path) | — | — | — |

Shape-change flags for the executor: `_run_tool` is the highest merge-conflict risk;
the loop turn path is now a state machine (`_state_build`/`_state_run`/`_state_save`/
`_state_respond`) with no 1:1 home for the inline `pre/post_llm_hook` — re-implement.
Rename privacy `TurnContext` → `PrivacyTurnContext` to avoid colliding with upstream's
loop `TurnContext`; carry it as hook-private state.

> Note (critique correction): `spawn.py` constructs its **own** `session_key`, so it
> does not flatly reuse the parent vault. The cross-run bleed risk Cap B addresses is
> `/goal`, `dream`, `cron`, and pairing — not `spawn`. Verify each derived path
> individually rather than asserting blanket reuse.

## Privacy Capabilities (大改 — all expressed as hook behavior, no upstream-file fork)

| Cap | What | Plugs into | Acceptance test |
|---|---|---|---|
| **A** | `StreamingSanitizer` with carry-over window (≥ longest entity span) | `ToolPrivacyInterceptor.sanitize_tool_result` | HIGH entity straddling a 4096-byte poll boundary → zero raw chars, placeholder reused; fuzz every byte offset of a 12KB stream |
| **B** | Scoped/keyed Vaults (`shared` / `ephemeral` child) | replace flat `_cache` in `core/state/vault.py`; created at run-key construction | ephemeral `/goal`/`dream` map never written to parent `maps/{user}.json`; cross-scope restore is a no-op |
| **C** | Explicit EgressPolicy + provider egress gate + at-rest `goal_state` sanitizer | `_tool_privacy_class` fall-through; wrap `FallbackProvider`; goal metadata | unregistered network-shaped tool → safe default + approval; non-allow-listed fallback never sees raw value; `/goal` objective persists placeholdered |
| **D** | Placeholder-stable compaction (`validate_placeholders`) | autocompact/consolidation hook | stubbed summarizer that drops/renumbers/emits-raw → rejected/repaired; counters never rewound |
| **E** | Multimodal egress gate for image-gen | thin wrapper at provider-factory time | reference image redacted + prompt placeholdered before bytes leave; fail-closed omits image |
| **F** | Privacy event side-channel (webui) + **localhost gate** | `_agent_ui.privacy` blob + `privacy_trace` event + additive `ws_http` route | round-trip re-validates; upstream client ignores privacy frames; **non-localhost client receives zero raw values** (blocking invariant) |

## WebUI Plan (summary)

- **Delete** the bespoke SPA: `webui/src/{App.tsx, app/**, pages/**, features/navigation/**,
  features/chat/**, components/ui/**, index.css}` and backend `cloakbot/channels/webui.py`.
- **Adopt** upstream `webui/` wholesale on its pinned stack (`components/thread/*`,
  `lib/{activity-timeline,workspace,tool-traces,nanobot-client}.ts`, i18n, providers).
- **Port** the privacy components into `webui/src/overlays/privacy/`: `types.ts`,
  `annotated-markdown.tsx`, `export-audit.ts`, `PrivacyStateProvider`, `PrivacyPanel`
  + `EntitySummary`/`PromptLog`/`ComputationLog`/`BlockedCounter`; **new**
  `privacy-client-lane.ts`, `PrivacyTraceRow`, `RestorationAnnotations`,
  `ToolApprovalPrompt`, `PipelineTimeline`, `privacy-overlay-mount.tsx`.
- **Dual WS contract on one socket:** upstream `{event:…}` frames render thread/
  activity/workspace; privacy rides `message`/`assistant_done` `.agent_ui.privacy`
  (zero upstream fork) + standalone `privacy_snapshot`/`privacy_trace`/`tool_approval`
  frames; history via additive `GET /api/sessions/{key}/privacy`.
- **5 frontend attach points (compose, do not fork):** `onPrivacy()` lane in
  `nanobot-client.ts`; `PrivacyTraceRow` in `AgentActivityCluster`; a ~3-line
  annotation slot on `MessageBubble.tsx`; `PrivacyPanel` dock in `App.tsx <main>`;
  `BlockedCounter` on `ConnectionBadge`.
- **UI-specific guards:** file-edit before/after stays server-local (only stats +
  `display_path` over the wire); reasoning text restored for display but excluded
  from remote-history; restoration offsets index the locally-restored string only.

## Execution Waves

Each wave's exit gate runs the privacy regression suite + the relevant leak-eval
(A1/A2/A3) at or below the pre-rebase baseline. `[BLOCKED-until X]` marks a hard
prerequisite.

### W0 — Rebase foundation (no features)

1. `git tag pre-rebase-snapshot`; archive current `webui/` + `channels/webui.py` as
   overlay reference → verify: tag exists, working tree clean.
2. `git remote add upstream https://github.com/HKUDS/nanobot.git && git fetch upstream`
   → verify: `git log upstream/main -1` resolves.
3. Branch `rebase/v0.2.1`; lay down `upstream/main` tree, keeping `cloakbot/privacy/**`,
   `cloakbot/tool_privacy.py`, `tests/{privacy,eval,security,sanitizer}/**`, `docs/**`
   → verify: tree contains upstream `apps/`, `pairing/`, `web/`, new tools.
4. Scripted `nanobot` → `cloakbot` rename pass (one isolated commit) → verify:
   `python -c "import cloakbot"` + privacy imports resolve.
5. Re-fork `webui/` from upstream on its pinned stack → verify:
   `cd webui && npm ci && npm run build` green.
6. Drop in `cloakbot/privacy/**` + `tool_privacy.py` unchanged → verify: imports clean.
7. Apply S-cost seams (1, 4, 6, 8, 10, 12, 11) as labeled commits → verify:
   `uv run pytest -m "not integration"` green at upstream parity.

**Exit gate:** repo imports clean; non-privacy non-integration suite green; privacy
package imports clean.

### W1 — Privacy hook re-architecture (the spine) — enables all else

1. Seam 2: `PrivacyHook(AgentHook)` + `before_turn` bracket on `_state_build`/
   `_state_respond`; rename `TurnContext` → `PrivacyTurnContext` → verify:
   `tests/privacy/` sanitize/restore tests.
2. Seam 3/5: `tool_privacy_interceptor` spec field + `_run_tool` prepare/sanitize
   bracket → verify: `tests/privacy/runtime/test_tool_interceptor.py`, runner tests.
3. Cap B scoped/keyed Vaults → verify: ephemeral-no-bleed test.
4. **Cap C DONE** [seam:9] — additive `cloakbot/privacy/egress_policy.py`
   `EgressPolicy` registry classifies tools by name/pattern (MCP/network-shaped →
   `EXTERNAL`+approval, fs-shaped → `LOCAL`, side-effecting locals →
   `SIDE_EFFECT`, unknown → fail-closed `EXTERNAL`+approval). Wired as the
   fall-through in `runner._tool_privacy_class` keyed on the authoritative
   `tool_name` (explicit per-tool `privacy_class` tag still wins). Provider egress
   gate `cloakbot/privacy/provider_egress_gate.py`
   (`EgressGatedFallbackProvider`) drops non-allow-listed fallbacks for any
   HIGH-severity-placeholder prompt; allow-list source =
   `agents.defaults.egress_fallback_allowlist`; installed in `providers/factory.py`.
   At-rest goal sanitizer `cloakbot/privacy/goal_at_rest.py` placeholders the
   persisted `/goal` objective via `replace_known_originals` (wired in
   `long_task.execute`). CLI-Anything (`run_cli_app`) defaults
   `EXTERNAL`+approval+per-app allow-list (D1); egress logged. Verified by
   `tests/privacy/runtime/test_egress_policy.py` (34 tests). One pre-existing
   interceptor test updated: its fictional `fetch_data` tool now correctly
   classifies `EXTERNAL`, so it uses the LOCAL `grep` tool to exercise the
   large-output sanitize path.

**Exit gate:** privacy regression suite green; **A1 text leak-eval at/below baseline.**

### W2 — WebUI parity + privacy side-channel — `[BLOCKED-until W1 / Cap B]`

1. Seam 7 / Cap F backend: re-home onto `channels/websocket.py`
   (`_agent_ui.privacy` + `privacy_trace`) + `webui/ws_http.py` additive routes +
   inbound `tool_approval` envelope; discard `channels/webui.py` → verify: round-trip
   + additive-ignore + rehydration + approval-inbound tests.
2. **Blocking invariant:** localhost gate + redacted projection for non-localhost
   connections (snapshot, HTTP route, approval) → verify: *non-localhost client
   receives zero raw values* test.
3. Move outbound token restoration into upstream outbound path (restore-local-only).
4. Cap F frontend: adopt Workbench; build the 5 overlay attach points → verify:
   `cd webui && npm run lint && npm run test && npm run build`.

**Exit gate:** Workbench renders without privacy code; overlay augments additively;
localhost-gate test green; webui lint/test/build green.

### W3 — Streaming + filesystem tools — `[BLOCKED-until Cap A + W1]`

1. Cap A `StreamingSanitizer` → verify: carry-over + byte-offset fuzz.
2. Tools: `exec_session`, `shell`/`long_task` streaming, `apply_patch`/`file_state`,
   filesystem parity; classify each via EgressPolicy → verify: tool tests.

**Exit gate:** Cap A acceptance + fuzz; **A3 long-doc leak-eval at/below baseline
(0/226 seam leaks must hold).**

### W4 — Sustained goals & autonomy — `[BLOCKED-until Cap B + Cap C + Cap D]`

1. `/goal` + `long_task` (Cap C at-rest `goal_state` sanitizer).
2. `autocompact` + `progress_hook` (Cap D).
3. `memory` hardening + `dream` refactor #3990 (Cap B ephemeral scopes + Cap D);
   keep `ephemeral` runs hooked (do **not** copy upstream's hook-skip).
4. `context`/`loader` (in-package `pkgutil` only, no `entry_points`)/`self.py`
   (hard-block the `cloakbot/privacy/` state surface from inspection).

**Exit gate:** Cap B `/goal` no-bleed; Cap D compaction-stability; A1 unchanged.

### W5 — Providers & model parity — `[BLOCKED-until Cap C provider gate]`

1. `fallback_provider` + factory + `model_presets` (model/provider immutable at
   runtime invariant defined here).
2. `bedrock` (gated behind explicit config + SECURITY note on env-driven egress).
3. `image_generation` (**also needs Cap E**); local backend first, remote behind gate.

**Exit gate:** Cap C provider-gate test; Cap E redaction/fail-closed; **A2 visual
leak-eval at/below baseline.**

### W6 — New channels & apps — `[BLOCKED-until Cap C classification]`

1. Channels `napcat` → `signal` (needs `pairing`, W7) → `msteams`; reconcile
   `channels/base.py`; lazy `discover_enabled()`. Keep channels dumb transports —
   no `cloakbot.privacy.*` import; route inbound media through `visual_redaction.py`.
2. Apps subsystem incl. CLI-Anything per D1 (default EXTERNAL + approval +
   per-app allow-list; no auto-install from model output; egress logged) + `cli_apps`/
   MCP-preset tooling.

**Exit gate:** every new channel/tool resolves to a safe EgressPolicy class (no
UNKNOWN→allow); full privacy suite + all three leak-evals green.

### W7 — Hardening

1. `pairing` (`nanobot/pairing/`) under Cap B ephemeral scopes; pairing codes
   high-entropy, single-use, TTL-expiring; code never enters a remote-bound payload.
2. `gateway_tokens`/`media_gateway`/`workspaces` parity.
3. Validate the sync runbook with a dry-run re-sync against fresh `upstream/main`.

**Exit gate:** full Validation suite at every layer; sync dry-run clean.

## W1b loop-seam design (execution-ready)

Integration points verified in upstream `agent/loop.py` (1764 lines; state machine
`_process_message:1183` → `_state_build:1380` → `_state_run:1426` → `_state_save:1460`
→ `_state_respond:1497`; `TurnContext:97`; `_run_agent_loop`→`AgentRunSpec(...):790`).

1. **Rename** privacy `TurnContext`→`PrivacyTurnContext` in `privacy/hooks/context.py` +
   all privacy importers (collides with upstream loop `TurnContext` at loop.py:97).
2. **`AgentLoop.__init__`:** add `set_vault_workspace(self.workspace)` [seam 6] (mirrors
   old loop.py:225-227).
3. **`TurnContext`:** add field `privacy_ctx: PrivacyTurnContext | None = None`.
4. **`_state_build` top (before `_build_initial_messages:1408` AND
   `_persist_user_message_early:1415`):** sanitize the turn so both the prompt and the
   persisted session see placeholders:
   `prepared, ctx.privacy_ctx = await pre_llm_hook(ctx.msg.content, ctx.session_key, media=ctx.msg.media or None, fail_open=True)`
   then `ctx.msg = dataclasses.replace(ctx.msg, content=<sanitized>, media=<redacted/[]>)`.
   TEXT path: `prepared` is a str. **MEDIA path (hard):** `prepared` is redacted content
   blocks — must reconcile with upstream's `_prepare_message_media` (ran in
   `_state_restore:1318`) and `_build_initial_messages` so raw images are never re-attached;
   **fail-closed if media present and the redacted-block route is not yet wired.**
5. **`_state_run`→`_run_agent_loop`→`AgentRunSpec:790`:** add a `tool_privacy_interceptor`
   param threaded to the spec: `tool_privacy_interceptor=ToolPrivacyInterceptor(ctx.privacy_ctx)`
   [seam 3].
6. **`_state_respond:1497` (before `_assemble_outbound`):**
   `ctx.final_content = await post_llm_hook(ctx.final_content, ctx.privacy_ctx, ctx.session_key, include_report=ctx.msg.channel != "webui")`.
7. **Streaming restoration (the load-bearing subtlety):** upstream streams deltas live via
   `AgentHook.on_stream`, so placeholders would flash to the user mid-stream. Two correct
   options: (a) a `PrivacyHook(AgentHook)` that buffers `on_stream` and flushes restored text
   at stream-end/`finalize_content` (mirrors old `_buffered_stream`/`_buffered_stream_end`),
   or (b) force non-streaming when `ctx.privacy_ctx.was_sanitized` (`on_stream=None` for that
   turn). **Ship (b) first (simple + leak-safe), upgrade to (a) for UX.** A restore only in
   `_state_respond` WITHOUT one of these LEAKS placeholders to the streamed UI — not acceptable.
8. **Approval flow** (`ToolApprovalRequiredError`→pending approval, old loop.py ~715) is
   W2-adjacent; until wired, non-LOCAL HIGH-severity tool turns fail-closed.

Gate: `tests/privacy/runtime` + `tests/privacy/agents` + a smoke turn asserting (1) provider
payload carries placeholders not raw values, (2) user-visible output is restored, (3) no raw
placeholder is ever streamed, (4) A1 leak-eval ≤ baseline.

## Validation

- [ ] `uv run pytest -m "not integration" tests/privacy/` — sanitizer/vault/runtime/
      protocol/webui unit + contract tests.
- [ ] `uv run pytest -m "not integration" tests/security/ tests/sanitizer/` — trust
      boundary + detection.
- [ ] `uv run pytest -m "not integration" tests/` — full non-integration suite.
- [ ] Per-capability acceptance tests A–F added under `tests/privacy/`.
- [ ] **Blocking:** non-localhost privacy side-channel client receives zero raw values.
- [ ] A1 text leak-eval (`tests/eval/runners/text_leak_eval.py` + `rollup.py`) ≤ baseline.
- [ ] A2 visual leak-eval (`visual_leak_eval.py`) ≤ baseline (span leak 1.11%).
- [ ] A3 long-doc leak-eval (`long_doc_leak_eval.py` + `long_doc_rollup.py`) ≤ baseline
      (pair leak 6.26%, **0/226 seam leaks**).
- [ ] `cd webui && npm run lint && npm run test && npm run build`.
- [ ] CI grep gate: privacy imports appear only in known seam files.

## References

- Local privacy assets (preserve verbatim): `cloakbot/privacy/**`,
  `cloakbot/tool_privacy.py`, `cloakbot/privacy/webui/{contracts,builders,history}.py`,
  `cloakbot/privacy/core/state/vault.py`, `cloakbot/privacy/runtime/{pipeline,tool_interceptor}.py`,
  `cloakbot/privacy/hooks/{context,pre_llm,post_llm}.py`, `cloakbot/privacy/transparency/report.py`.
- Local forks to discard/re-express: `cloakbot/agent/loop.py` (inline privacy calls),
  `cloakbot/agent/runner.py` (port the clean `ToolPrivacyInterceptorProtocol`),
  bespoke `cloakbot/channels/webui.py`, bespoke `webui/src/features/{chat,privacy,navigation}`.
- Upstream targets: `agent/loop.py` (`_state_build`, `_state_run`, `_state_respond`,
  `AgentRunSpec(...)`), `agent/runner.py` (`AgentRunSpec`, `_run_tool`, `_classify_violation`,
  `hook = spec.hook`), `channels/websocket.py` (`OUTBOUND_META_AGENT_UI`, `_send_event`,
  `_dispatch_envelope`, `agent_ui` passthrough, `_is_localhost`), `webui/ws_http.py`
  (`GatewayHTTPHandler` routes), `agent/hook.py`, `session/manager.py`.
- Test gates / baselines: `tests/{privacy,security,sanitizer,eval}/**`, A1/A2/A3
  baselines in `docs/HACKATHON_WRITEUP.md` and `tests/eval/reports/`.
