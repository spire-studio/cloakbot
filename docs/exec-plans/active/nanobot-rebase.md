# Nanobot Rebase + Privacy Overlay (Full Parity)

## Goal

Re-fork the core from upstream `HKUDS/nanobot@main` (v0.2.1+ "Workbench") to reach
full feature parity, re-express the privacy kernel as a clean **additive overlay**
(one `PrivacyHook` + one tool-IO interceptor + one privacy WebSocket subclass +
one frontend `overlays/privacy/`), and rework the privacy pipeline internals
(streaming sanitizer, scoped vaults, egress policy, stable compaction, multimodal
egress, webui side-channel) so the previously-gated features become safe to ship.

## Status

- Created: 2026-06-04. State: **planning complete, execution not started.**
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
4. Cap C EgressPolicy registry + tool classification fall-through → verify:
   unregistered-tool-safe-default test.

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
