<p align="center">
  <img src="logo+cloakbot-readme.png" alt="CloakBot" width="420" />
</p>

<h1 align="center">Cloakbot: Privacy-Preserving AI Agent</h1>

<p align="center">A local multi-agent privacy solution between your data and any remote LLM.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Privacy-First-0F172A?style=flat-square" alt="Privacy First" />
  <img src="https://img.shields.io/badge/Gemma%204-Local%20Detection-0F9D58?style=flat-square" alt="Gemma 4 Local Detection" />
  <img src="https://img.shields.io/badge/vLLM-OpenAI%20Compatible-1F6FEB?style=flat-square" alt="vLLM OpenAI Compatible" />
  <img src="https://img.shields.io/badge/Multi--Agent-Hybrid-7C3AED?style=flat-square" alt="Hybrid Multi-Agent" />
  <img src="https://img.shields.io/badge/Remote%20LLM-Claude%20%7C%20GPT%20%7C%20Gemini-8B5CF6?style=flat-square" alt="Remote LLM Claude GPT Gemini" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A?style=flat-square" alt="MIT License" />
</p>

<p align="center"><strong>English</strong> | <a href="README.zh-CN.md">简体中文</a></p>

<p align="center"><sub>Built on <a href="https://github.com/HKUDS/nanobot">nanobot</a> · Submitted to the <strong>Gemma 4 Good Hackathon</strong> (Kaggle, May 2026)</sub></p>

CloakBot adds a **local privacy pipeline** between your session and any remote LLM. Before a message is sent upstream, a multi-agent system powered by trusted local model served through vLLM/Ollama runs two local JSON-only detectors: one for general sensitive entities and one for sensitive numeric or temporal values. Matched spans are rewritten into typed, reversible placeholders and stored in a session-scoped Vault. For math task turns, the remote LLM is asked for structure only while the real arithmetic happens locally with the original values from the Vault.

After the remote LLM responds, CloakBot restores placeholders locally and appends a per-turn privacy report. Streaming output is buffered until that post-processing completes, so the user does not see raw placeholders.

---

## Table of Contents

- [How It Works](#how-it-works)
- [What Gets Detected](#what-gets-detected)
- [Multi-Agent System Design](#multi-agent-system-design)
- [Architecture](#architecture)
- [Roadmap](#roadmap)
- [Engineering Knowledge Base](#engineering-knowledge-base)
- [Setup](#setup)
- [Running Tests](#running-tests)
- [Design Decisions](#design-decisions)
- [Hackathon Tracks](#hackathon-tracks)
- [Credits & License](#credits--license)

---

## How It Works

```
User message
  └─► [pre_llm_hook → PrivacyRuntime]
        • Run GeneralPrivacyDetector + DigitPrivacyDetector locally via vLLM
        • Replace sensitive spans with typed tokens  e.g. "Alice" → <<PERSON_1>>
        • Persist session Vault (token ↔ raw mapping, plus numeric values when needed)
        • Classify intent locally (chat / math)
        • Route turn to ChatAgent or MathAgent
  └─► [Remote LLM — Claude / GPT / Gemini]
        • Receives sanitized prompt only
        • For math turns: receives an extra contract to emit <python_snippet_N> blocks
        • Responds using placeholders instead of raw values
        • Tool results are sanitized before reuse in later model calls
  └─► [post_llm_hook → local post-processing]
        • Execute arithmetic-only math snippets with real values from Vault
        • Restore <<PERSON_1>> → "Alice"
        • Render per-turn privacy report
  └─► User sees original values in the final reply
```

---

## What Gets Detected

| Category | Examples | Default Severity |
|---|---|---|
| Personal and contact data | Names, phone numbers, emails, physical addresses | High |
| Unique or private identifiers | SSNs, passports, account numbers, license plates | High |
| Secrets and access data | Passwords, API keys, private tokens, sensitive URLs | High |
| Organization and network context | Company names, school names, IP addresses | High |
| Medical and private narrative data | PHI, treatments, confidential plans, code names, other sensitive free text | High |
| Sensitive numeric and temporal data | Money, dates, percentages, counts, measurements, scores, coordinates | High |

The detector is split into two local passes: `GeneralPrivacyDetector` for non-computable text spans and `DigitPrivacyDetector` for numeric or temporal values that may need local computation later. The built-in registry currently marks all shipped entity families as `high` severity.

### Token Schema

All entities are replaced using the pattern `<<ENTITY_TYPE_INDEX>>`, producing consistent, readable tokens:

| Raw Value | Token | Severity |
|---|---|---|
| `Alice Chen` | `<<PERSON_1>>` | High |
| `alice@acme.com` | `<<EMAIL_1>>` | High |
| `555-123-4567` | `<<PHONE_1>>` | High |
| `123-45-6789` | `<<ID_1>>` | High |
| `$142,500` | `<<FINANCE_1>>` | High |
| `December 15, 2026` | `<<DATE_1>>` | High |
| `15%` | `<<PERCENTAGE_1>>` | High |
| `Stanford Hospital` | `<<ORG_1>>` | High |
| `Metformin 500mg` | `<<MEDICAL_1>>` | High |

Indexed per type so the remote LLM can still track relationships between entities (e.g. `PERSON_1` and `PERSON_2` are different people) without knowing who they are.

---

## Multi-Agent System Design

CloakBot uses a **hybrid multi-agent architecture** inside the privacy layer: a local Orchestrator coordinates detector, routing, chat, and math behaviors around the remote LLM call. The remote LLM is treated as an untrusted compute resource — it only ever receives sanitized text.

### Trust Boundary

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LOCAL TRUST ZONE                             │
│                                                                     │
│   User ──► [ pre_llm_hook ]                                         │
│                  │                                                  │
│                  ▼                                                  │
│         [ PrivacyRuntime ]                                          │
│            /         |         \                                    │
│           ▼          ▼          ▼                                   │
│  [PiiDetector] [IntentAnalyzer] [TurnContext/Vault]                 │
│      /    \             │             │                             │
│     ▼      ▼            ▼             ▼                             │
│ [General] [Digit]   [TaskRouter]   [Handler]                        │
│    via      via        /   \           │                            │
│  Gemma 4  Gemma 4     ▼     ▼          ▼                            │
│   vLLM     vLLM   [Chat] [Math]   [Session Vault]                   │
│                          │        (JSON-backed placeholder map)     │
│                          ▼                                          │
│                 [Local Math Executor]                               │
│                                                                     │
└──────────────────┬──────────────────────────────────────────────────┘
                   │  sanitized payload only
   ────────────────┼──────────── REMOTE BOUNDARY ─────────────────────
                   ▼
            [ Remote LLM ]  (Claude / GPT / Gemini APIs)
                   │
   ────────────────┼─────────────────────────────────────────────────
                   │  response re-enters local trust zone
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    POST-RESPONSE LOCAL PIPELINE                      │
│                                                                      │
│   [ MathAgent ]      ← executes <python_snippet_N> blocks locally    │
│           │                                                          │
│   [ Restorer ]       ← swap tokens back using Vault                  │
│           │                                                          │
│   [ Transparency Report ]  ← summarize masked input/tool entities    │
│           │                                                          │
└───────────┼──────────────────────────────────────────────────────────┘
            ▼
         Output → User ✓
```

Document and dataset work is handled through normal chat/tool turns. Local tools
may read raw files, but tool results are sanitized before they are reused by the
remote model.

### Agents

| Agent | Role | Model |
|---|---|---|
| **PrivacyRuntime** | Coordinates one turn end-to-end: sanitize, classify intent, route, restore, report | Python runtime pipeline |
| **PiiDetector** | Runs the general detector and digit detector concurrently, then deduplicates results | Gemma 4 via vLLM |
| **GeneralPrivacyDetector** | Extracts non-computable sensitive spans such as names, IDs, secrets, org names | Gemma 4 via vLLM |
| **DigitPrivacyDetector** | Extracts sensitive numeric/temporal spans and normalizes values for later math | Gemma 4 via vLLM |
| **IntentAnalyzer** | Classifies turns as `chat` or `math` | Gemma 4 via vLLM |
| **Handler + Vault** | Applies `<<TAG_N>>` placeholders and persists the session mapping | Rule-based + JSON file |
| **ChatAgent** | Sends sanitized text upstream and returns the response unchanged until restoration | Rule-based |
| **MathAgent** | Adds the snippet contract before the remote call and executes validated snippets locally after the call | Remote LLM + local executor |
| **Restorer** | Restores placeholders with a single regex pass | Rule-based |
| **Transparency Report** | Renders a per-turn markdown summary of masked entities | Rule-based |
| **ToolPrivacyInterceptor** | Restores local tool inputs, gates sensitive non-local tool calls, and sanitizes tool outputs, including file/document reads, before model reuse | Rule-based + detector |
| **ToolPrivacyDetector** | Chunked, content-type-aware detection over long tool outputs (read_file, web_fetch, MCP JSON). Per-chunk concurrency + timeout, cross-chunk dedup, fail-closed on partial chunk failure | Gemma 4 via vLLM |
| **Chunkers** (`chunking/`) | Content-aware splitting — plaintext (paragraph + overlap), JSON (path-flatten), HTML (meta + mailto + body), Markdown (heading + fence-aware) | Rule-based |
| **VisualPrivacyPipeline** (`visual_redaction.py`) | Visual detection + OCR-anchored bbox redaction with placeholder-text overlay rendered inside each black bar; sibling region-map text block; cross-modal recall bridge (text-side entities forwarded as visual needles, visual placeholders back-substituted into OCR text); fail-closed default | Gemma 4 via vLLM + Pillow + Tesseract |

### Detector Passes (Defense in Depth)

The current runtime enforces input sanitization before the remote LLM call and
tool-output sanitization when tool calls are routed through the privacy
interceptor. Restored remote-model responses are not re-detected by design.

```
Pass 1  user input             → prevent raw PII from leaving device
Pass 1b user-attached images   → same, but routed through the visual pipeline
Pass 2  tool call output       → sanitize results before model reuse
Pass 2b large tool outputs     → chunked detection + cross-chunk vault coalesce
Pass 2c visual tool results    → OCR + visual placeholder overlay + region map
```

Long tool outputs (read_file on a big markdown, a web_fetch HTML page, MCP JSON)
cross a configurable threshold into `ToolPrivacyDetector`, which sniffs the
content type, splits via the matching chunker, runs the local detector
concurrently per chunk under a per-chunk timeout, then dedupes detected
entities so the same email seen in chunks #2 and #7 lands on one
placeholder. If any chunk fails (timeout, malformed model output), the
interceptor fails closed and replaces the payload with a text placeholder
rather than forwarding a partially-detected result.

User-attached images and image-bearing tool results share `process_visual_blocks`,
which (a) runs OCR + text-side sanitize first so the Vault has placeholders
ready, (b) feeds text-side entities into the visual matcher as additional
needles to cover spans the multimodal model overlooked, (c) renders each
vault placeholder *inside* its redaction box so the remote model can refer to
redacted regions by name, (d) appends a region-map text block per image, and
(e) back-substitutes any newly-allocated placeholder into the OCR sanitized
text so the two modalities ship the same view.

`ToolPrivacyInterceptor` also restores placeholders before local tool execution
and requests approval when sensitive restored arguments would be sent to
non-local or side-effecting tools. Strings that are entirely vault placeholders
short-circuit detection to prevent nested-token corruption.

### Math Privacy (Goal 2)

For computation tasks, the remote LLM acts as a **reasoning engine only** — it never sees actual numbers:

```
Input:   "My salary is $142,500. What is 18% of it?"
Masked:  "What is 18% of <<FINANCE_1>>?" + snippet contract
Remote:  "<python_snippet_1>result = FINANCE_1 * 0.18</python_snippet_1>"
Local:   result = 142500 * 0.18          # real value substituted from Vault
Output:  "$25,650.00"
```

The local executor is deliberately narrow: it parses the snippet as Python AST, only allows arithmetic expressions assigned to `result`, exposes only a few safe numeric helpers (`abs`, `round`, `min`, `max`, `pow`), and rejects unknown variables or chained exponentiation.

### Document & Dataset Privacy (Goal 3)

Document privacy is part of tool privacy, not a separate document-worker pipeline.
When the agent needs file, document, or dataset content, it uses local tools such
as `read_file`, `grep`, or future structured readers. Those tools may inspect
raw local content, but `ToolPrivacyInterceptor.sanitize_tool_result()` sanitizes
the result before it is sent back to the remote model.

This keeps one trust boundary for every tool-sourced document:

```
local tool reads raw document
  → tool result is sanitized with the session Vault
  → remote model receives sanitized content only
  → final user-visible answer may be restored locally
```

### Tool Call Privacy (Goal 4)

Tool privacy is implemented through `ToolPrivacyInterceptor` and tool privacy
classes:

```
Implemented today:
  sanitize_tool_output(text, session_key)
  ToolPrivacyInterceptor.prepare_tool_call(...)
  ToolPrivacyInterceptor.sanitize_tool_result(...)
  TurnContext.tool_output_entities
  ToolApprovalRequest for sensitive non-local tool inputs
```

Tool classes declare `local`, `external`, or `side_effect` privacy behavior.
External and side-effecting tools should receive the least permissive accurate
class.

---

## Architecture

```
cloakbot/
├── cloakbot/
│   ├── privacy/                 ← CloakBot's privacy layer
│   │   ├── core/
│   │   │   ├── detection/
│   │   │   │   ├── detector.py      General + digit detector facade (user input)
│   │   │   │   ├── tool_detector.py Chunked tool-output detector + per-chunk concurrency / timeout / fail-closed signal
│   │   │   │   ├── chunking/
│   │   │   │   │   ├── base.py          Chunker protocol + Chunk dataclass
│   │   │   │   │   ├── sniffer.py       Content-type sniffer (text/json/html/markdown)
│   │   │   │   │   ├── text.py          Paragraph-aware plaintext chunker + overlap window
│   │   │   │   │   ├── json_chunker.py  JSON path-flatten chunker
│   │   │   │   │   ├── html.py          HTML chunker (meta + mailto + visible body)
│   │   │   │   │   └── markdown.py      Markdown chunker (heading split, fence-aware)
│   │   │   │   ├── general_detector.py  Non-computable entity extraction via local vLLM (invoice-aware prompt)
│   │   │   │   ├── digit_detector.py    Sensitive numeric/temporal extraction via local vLLM (unit/multiplier-aware)
│   │   │   │   └── llm_json.py      JSON completion helpers for local models
│   │   │   ├── sanitization/
│   │   │   │   ├── sanitize.py      Public sanitize/remap entry points (+ sanitize_tool_output_chunked)
│   │   │   │   ├── handler.py       Placeholder-safe token application
│   │   │   │   ├── restorer.py      Reverse lookup and restoration
│   │   │   │   └── alias_resolver.py  Reuse placeholders across turns (PERSON + ORG substring, NFKC-normalised)
│   │   │   ├── math/
│   │   │   │   ├── math_executor.py Remote snippet contract + local execution
│   │   │   │   └── math_helpers.py  AST validation for arithmetic-only snippets
│   │   │   └── state/
│   │   │       └── vault.py         Session-scoped token/value map on disk
│   │   ├── runtime/
│   │   │   ├── pipeline.py      Top-level privacy coordinator (prepare_turn(text, media=...))
│   │   │   ├── routing.py       chat/math routing
│   │   │   ├── registry.py      Worker registration and lookup
│   │   │   └── tool_interceptor.py  Tool input/output privacy boundary + chunked routing + severity-driven approval
│   │   ├── visual_redaction.py  Visual detection + OCR-anchored redaction + placeholder overlay + region map + cross-modal recall bridge
│   │   ├── agents/
│   │   │   ├── classification/
│   │   │   │   └── intent_analyzer.py   Local intent classification
│   │   │   └── workers/
│   │   │       ├── chat_agent.py    Standard sanitized chat flow
│   │   │       └── math_agent.py    Local execution of remote-generated snippets
│   │   ├── hooks/
│   │   │   ├── pre_llm.py           Sanitize before the remote LLM call (now accepts media=...)
│   │   │   ├── post_llm.py          Restore after the remote LLM call
│   │   │   └── context.py           Turn-scoped privacy state (incl. user_input_visual_redactions / vault_artifacts)
│   │   └── transparency/
│   │       └── report.py            Per-turn privacy report rendering
│   ├── providers/
│   │   └── vllm.py                  OpenAI-compatible client → trusted vLLM server
│   └── agent/
│       └── loop.py                  Sanitization middleware (2 hooks)
├── tests/
│   ├── privacy/                     Privacy-layer unit tests
│   └── sanitizer/                   Older sanitizer compatibility / integration tests
└── scripts/
    └── start_vllm.sh                Start vLLM server
```

Session-level placeholder mappings are persisted as JSON under `~/.cloakbot/workspace/privacy_vault/maps/`, so the Vault can reuse the same placeholder mapping across turns in the same session. CloakBot now supports **multi-turn conversation privacy** by carrying forward placeholder mappings across turns while still restoring user-visible outputs locally. Computable placeholders also store normalized values for later local math execution.

---

## Roadmap

### ✅ v0.1 — Privacy Runtime Foundation (Current, April 2026)
- [x] Split detectors for general entities and numeric/temporal entities
- [x] Redact+Tokenize with `<<ENTITY_TYPE_N>>` placeholders
- [x] Session Vault with JSON persistence
- [x] Final output restoration via placeholder remap
- [x] Web UI chat interface
- [x] PrivacyRuntime with turn-scoped context
- [x] Local intent analysis and chat/math routing
- [x] MathAgent snippet contract plus local arithmetic execution
- [x] Multi-turn conversation privacy protection
- [x] Web UI polish and usability improvements
- [x] ToolPrivacyInterceptor for tool input restoration and output sanitization

### 🔨 v0.2 — Trust Boundary Expansion
- [ ] Chunked sanitization for large file/document tool outputs
- [ ] Dataset/table-specific tool output sanitization

### 🚀 v0.3 — Production Readiness
- [ ] Encrypted Vault persistence option
- [ ] Faster detector path / smaller local models
- [ ] Better bilingual and quasi-identifier coverage
- [ ] Policy-driven handling beyond the current registry defaults
- [ ] Full end-to-end privacy integration tests

---

## Engineering Knowledge Base

Agent-oriented architecture, reliability, security, and privacy-domain notes now
live under [`docs/`](docs/README.md). Start with [`AGENTS.md`](AGENTS.md) for the
short harness entry point, then follow the specific docs needed for the task.

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env:
#   VLLM_BASE_URL=http://<your-vllm-server>:8000/v1
#   VLLM_API_KEY=your-secret-token
#   VLLM_MODEL=google/gemma-4-E2B-it
```

Set up the remote LLM (Claude, GPT, Gemini, etc.) in `~/.cloakbot/config.json` as usual for cloakbot or using `onboard`:

```bash
uv run python -m cloakbot onboard
```

### 3. Start the local Gemma 4 backend — pick ONE

CloakBot uses one OpenAI-compatible client for both backends, so the `VLLM_*` variable names in `.env` work for either profile (they're historical).

#### Option A: vLLM (Ubuntu / GPU machine) — fast, reproducible

```bash
# First time: install vllm and authenticate with HuggingFace
uv sync --extra vllm
uv run huggingface-cli login          # accept Gemma license at hf.co/google/gemma-4-E2B-it

# Start server (reads VLLM_API_KEY and VLLM_MODEL from .env automatically)
bash scripts/start_vllm.sh
```

This is the path we use to produce the A1 / A2 / A3 eval reports.

#### Option B: Ollama (macOS / Linux / WSL) — no GPU required

```bash
# First time:
#   curl -fsSL https://ollama.com/install.sh | sh

bash scripts/start_ollama.sh
```

The script pulls `gemma4:e2b` (~5 GB), starts the daemon, and warms the model. Ollama exposes an OpenAI-compatible endpoint at `http://127.0.0.1:11434/v1`. Then set in `.env`:

```bash
VLLM_BASE_URL=http://127.0.0.1:11434/v1
VLLM_API_KEY=ollama        # Ollama doesn't enforce auth; any value works
VLLM_MODEL=gemma4:e2b
```

This is the path we recommend for real-world adoption — CloakBot's privacy kernel runs on a 2019 MacBook Air.

> Either backend exposes the same OpenAI-compatible surface. CloakBot's sanitizer uses it exclusively for PII detection — the remote LLM call (Claude / GPT / Gemini) is completely separate.

### 4. Start the WebUI

```bash
uv run python -m cloakbot webui
# Gateway   : http://127.0.0.1:8000
# Frontend  : http://127.0.0.1:5173
```

### Or, one-command demo

```bash
bash scripts/quickstart_demo.sh
```

Starts Ollama + bootstraps `.env` + launches the WebUI + opens your browser. Drag `docs/demo/demo_onboarding_memo.md` into the Composer to see the full Local↔Remote pipeline in action.

---

## Design Decisions

**Redact + Tokenize, not Pseudonymize** — `<<PERSON_1>>` is simpler and safer than replacing names with fake-but-realistic names. The remote LLM can still track relationships between `PERSON_1` and `PERSON_2` without learning who they are.

**Two local detectors, one Vault** — CloakBot separates non-computable spans from numeric or temporal spans so it can both preserve task structure and keep enough normalized data locally for later math execution.

**Remote LLM as reasoning engine only for math** — math turns ask the remote model for structure in `<python_snippet_N>` blocks; the final numeric answer is computed locally against Vault values.

**Fail-open by default** — if the local vLLM server is unreachable, the current default is to pass the message through unchanged rather than block the turn. The sanitizer APIs also support strict fail-closed behavior.

**Streaming-safe post-processing** — the CLI buffers streamed output until math execution, restoration, and report rendering are finished. The user sees the finalized answer, not intermediate placeholders.

**Hook-based integration** — the privacy layer is largely isolated under `cloakbot/privacy/` and integrates into the main runtime through `pre_llm_hook` and `post_llm_hook` in [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574).

**Documents are tool-sourced privacy data** — there is no separate document intent or document worker. Document and dataset protection belongs at the tool output boundary so file reads, grep results, and future structured readers all share the same sanitizer/Vault path.

---

## Hackathon Tracks

- **Main Track — Gemma 4 Good (Safety & Trust direction)**: Gemma 4 E2B as a local privacy kernel that enforces a pre-wire boundary before any byte reaches the remote LLM. Backed by 2,872 entity-test instances of receipts across A1 (text), A2 (visual), and A3 (long-document) leak evals — see [`docs/HACKATHON_WRITEUP_DRAFT.md`](docs/HACKATHON_WRITEUP_DRAFT.md).
- **Ollama Special Technology**: `bash scripts/start_ollama.sh` ships the model + the OpenAI-compatible endpoint in one tool — no GGUF wrangling, no per-OS Metal/CUDA forks. **Gemma 4 is the trust layer; Ollama is the deployment layer.** Try it: `bash scripts/quickstart_demo.sh`.

---

## Credits & License

CloakBot is built on [nanobot](https://github.com/HKUDS/nanobot) (MIT License) by HKUDS. The channel integrations, session management, memory system, and CLI come from the upstream framework. CloakBot's privacy-specific work in this repo lives primarily under `cloakbot/privacy/`, [vllm.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/providers/vllm.py:1), and the hook integration points in [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574).
