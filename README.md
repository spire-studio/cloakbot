<p align="center">
  <img src="logo+cloakbot.png" alt="CloakBot" width="320" />
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

CloakBot adds a **local privacy pipeline** between your session and any remote LLM. Before a message is sent upstream, a trusted Gemma 4 model served through vLLM runs two local JSON-only detectors: one for general sensitive entities and one for sensitive numeric or temporal values. Matched spans are rewritten into typed, reversible placeholders and stored in a session-scoped Vault. For math turns, the remote LLM is asked for structure only while the real arithmetic happens locally with the original values from the Vault.

After the remote LLM responds, CloakBot restores placeholders locally and appends a per-turn privacy report. Streaming output is buffered until that post-processing completes, so the user does not see raw placeholders.

---

## Table of Contents

- [How It Works](#how-it-works)
- [What Gets Detected](#what-gets-detected)
- [Multi-Agent System Design](#multi-agent-system-design)
- [Architecture](#architecture)
- [Roadmap](#roadmap)
- [Setup](#setup)
- [Running Tests](#running-tests)
- [Design Decisions](#design-decisions)
- [Hackathon Tracks](#hackathon-tracks)
- [Credits & License](#credits--license)

---

## How It Works

```
User message
  └─► [pre_llm_hook → PrivacyOrchestrator]
        • Run GeneralPrivacyDetector + DigitPrivacyDetector locally via vLLM
        • Replace sensitive spans with typed tokens  e.g. "Alice" → <<PERSON_1>>
        • Persist session Vault (token ↔ raw mapping, plus numeric values when needed)
        • Classify intent locally (chat / math / doc)
        • Route turn to ChatAgent or MathAgent
  └─► [Remote LLM — Claude / GPT / Gemini]
        • Receives sanitized prompt only
        • For math turns: receives an extra contract to emit <python_snippet_N> blocks
        • Responds using placeholders instead of raw values
  └─► [post_llm_hook → local post-processing]
        • Execute arithmetic-only math snippets with real values from Vault
        • Restore <<PERSON_1>> → "Alice"
        • Render per-turn privacy report
  └─► User sees original values in the final reply
```

**Example — Chat**

```
You:        My name is Alice Chen, email alice@acme.com. What's my name?
🔒 Masked:  "Alice Chen" [PERSON, high] → <<PERSON_1>>
            "alice@acme.com" [EMAIL, high] → <<EMAIL_1>>
CloakBot:   Your name is Alice Chen.
📋 Report:  2 entities masked in input · all restored ✓
```

**Example — Math**

```
You:        My salary is $142,500. What is 18% of it?
🔒 Masked:  "$142,500" [FINANCE, high] → <<FINANCE_1>> · "18%" passes through
Sent:       "What is 18% of <<FINANCE_1>>?" + privacy math snippet instructions
Remote:     "<python_snippet_1>result = FINANCE_1 * 0.18</python_snippet_1>"
Local exec: result = 142500 * 0.18 = 25650
CloakBot:   18% of $142,500 is $25,650.00
📋 Report:  1 entity masked · computed locally · all restored ✓
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
│         [ PrivacyOrchestrator ]                                     │
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

`Intent.DOC` already exists in the router, but there is no `DocAgent` yet. Document turns currently fall back to `ChatAgent`.

### Agents

| Agent | Role | Model |
|---|---|---|
| **PrivacyOrchestrator** | Coordinates one turn end-to-end: sanitize, classify intent, route, restore, report | Python orchestrator |
| **PiiDetector** | Runs the general detector and digit detector concurrently, then deduplicates results | Gemma 4 via vLLM |
| **GeneralPrivacyDetector** | Extracts non-computable sensitive spans such as names, IDs, secrets, org names | Gemma 4 via vLLM |
| **DigitPrivacyDetector** | Extracts sensitive numeric/temporal spans and normalizes values for later math | Gemma 4 via vLLM |
| **IntentAnalyzer** | Classifies turns as `chat`, `math`, or `doc` | Gemma 4 via vLLM |
| **Handler + Vault** | Applies `<<TAG_N>>` placeholders and persists the session mapping | Rule-based + JSON file |
| **ChatAgent** | Sends sanitized text upstream and returns the response unchanged until restoration | Rule-based |
| **MathAgent** | Adds the snippet contract before the remote call and executes validated snippets locally after the call | Remote LLM + local executor |
| **Restorer** | Restores placeholders with a single regex pass | Rule-based |
| **Transparency Report** | Renders a per-turn markdown summary of masked entities | Rule-based |
| **Tool Interceptor** | Reserved for future tool-output enforcement; currently a placeholder file | Not implemented yet |

### Detector Passes (Defense in Depth)

The current runtime performs **one mandatory detector pass before the remote LLM call**:

```
Pass 1  user input        → prevent raw PII from leaving device
Pass 2  LLM response      → planned, not wired yet
Pass 3  tool call output  → helper exists, interceptor not wired yet
```

`sanitize_tool_output()` and `tool_output_entities` already exist in the codebase, so the extension points are there. What is implemented today is input-side sanitization plus post-response restoration and math execution.

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

This part of the README was ahead of the code. The current implementation does **not** ship a document or dataset privacy pipeline yet.

What exists today:
1. The intent analyzer can classify a turn as `doc`.
2. The router preserves that intent.
3. `get_agent()` logs a warning and falls back to `ChatAgent` because `DocAgent` is not implemented yet.

So document privacy is a roadmap item, not a current feature.

### Tool Call Privacy (Goal 4)

Tool privacy is also only **partially scaffolded** right now:

```
Implemented today:
  sanitize_tool_output(text, session_key)  → reusable helper
  TurnContext.tool_output_entities         → report slot

Not wired yet:
  agents/tool_interceptor.py               → placeholder
  main tool loop pass 3 enforcement        → pending
```

So CloakBot already has the core sanitizer entry point for tool results, but the main agent loop does not yet run every tool output through it.

---

## Architecture

```
cloakbot/
├── cloakbot/
│   ├── privacy/                 ← CloakBot's privacy layer
│   │   ├── core/
│   │   │   ├── detector.py          General + digit detector facade
│   │   │   ├── general_detector.py  Non-computable entity extraction via local vLLM
│   │   │   ├── digit_detector.py    Sensitive numeric/temporal extraction via local vLLM
│   │   │   ├── handler.py           Placeholder-safe token application
│   │   │   ├── vault.py             Session-scoped token/value map on disk
│   │   │   ├── restorer.py          Reverse lookup and restoration
│   │   │   ├── sanitize.py          Public sanitize/remap entry points
│   │   │   ├── math_executer.py     Remote snippet contract + local execution
│   │   │   └── math_helpers.py      AST validation for arithmetic-only snippets
│   │   ├── agents/
│   │   │   ├── orchestrator.py      Top-level privacy coordinator
│   │   │   ├── intent_analyzer.py   Local intent classification
│   │   │   ├── task_router.py       chat/math/doc routing
│   │   │   ├── chat_agent.py        Standard sanitized chat flow
│   │   │   ├── math_agent.py        Local execution of remote-generated snippets
│   │   │   └── tool_interceptor.py  Placeholder for future tool-output enforcement
│   │   ├── hooks/
│   │   │   ├── pre_llm.py           Sanitize before the remote LLM call
│   │   │   ├── post_llm.py          Restore after the remote LLM call
│   │   │   └── context.py           Turn-scoped privacy state
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
    ├── start_vllm.sh                Start vLLM server
    └── test_sanitizer.py            Smoke test
```

Session-level placeholder mappings are persisted as JSON under `~/.cloakbot/sanitizer_maps/`, so the Vault can reuse the same placeholder mapping across turns in the same session. That said, the current end-to-end privacy boundary is still **single-turn**: restored conversation history is persisted back into the session, so full multi-turn conversation privacy remains a roadmap item. Computable placeholders also store normalized values for later local math execution.

---

## Roadmap

### ✅ v0.1 — Privacy Runtime Foundation (Current, April 2026)
- [x] Split detectors for general entities and numeric/temporal entities
- [x] Redact+Tokenize with `<<ENTITY_TYPE_N>>` placeholders
- [x] Session Vault with JSON persistence
- [x] Final output restoration via placeholder remap
- [x] Web UI chat interface
- [x] `pre_llm_hook` and `post_llm_hook` wired into `cloakbot/agent/loop.py`
- [x] PrivacyOrchestrator with turn-scoped context
- [x] Local intent analysis and chat/math/doc routing
- [x] MathAgent snippet contract plus local arithmetic execution
- [ ] Web UI polish and usability improvements

### 🔨 v0.2 — Trust Boundary Expansion
- [ ] Multi-turn conversation privacy protection
- [ ] Tool-use Detector: enforce tool-use sanitization in the main loop
- [ ] Real `ToolInterceptor` implementation
- [ ] Concrete `DocAgent` implementation
- [ ] Chunk-map-aggregate document flow with shared Vault
- [ ] Dataset-specific schema and column sanitization

### 🚀 v0.3 — Production Readiness
- [ ] Encrypted Vault persistence option
- [ ] Faster detector path / smaller local models
- [ ] Better bilingual and quasi-identifier coverage
- [ ] Policy-driven handling beyond the current registry defaults
- [ ] Full end-to-end privacy integration tests

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync                                           # install cloakbot dependencies
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env:
#   VLLM_BASE_URL=http://<your-vllm-server>:8000/v1
#   VLLM_API_KEY=your-secret-token
#   VLLM_MODEL=google/gemma-4-E2B-it
```

Set up the remote LLM (Claude, GPT, Gemini, etc.) in `~/.cloakbot/config.json` as usual for cloakbot.

### 3. Start the vLLM server (Ubuntu / GPU machine)

```bash
# First time: install vllm and authenticate with HuggingFace
uv sync --extra vllm
uv run huggingface-cli login          # accept Gemma license at hf.co/google/gemma-4-E2B-it

# Start server (reads VLLM_API_KEY and VLLM_MODEL from .env automatically)
bash scripts/start_vllm.sh
```

> The vLLM server exposes an OpenAI-compatible API. CloakBot's sanitizer uses it exclusively for PII detection — the remote LLM call is completely separate.

### 4. Verify the sanitizer

```bash
uv run python scripts/test_sanitizer.py
```

### 5. Chat

```bash
uv run python -m cloakbot agent --config ~/.cloakbot/config.json
```

---

## Running Tests

```bash
# Privacy unit tests (mocked vLLM + Vault)
uv run --extra dev pytest tests/privacy/ -v

# Sanitizer compatibility / round-trip tests
uv run --extra dev pytest tests/sanitizer/ -v

# Integration tests (requires a running vLLM server)
uv run --extra dev pytest tests/ -m integration -v
```

---

## Design Decisions

**Redact + Tokenize, not Pseudonymize** — `<<PERSON_1>>` is simpler and safer than replacing names with fake-but-realistic names. The remote LLM can still track relationships between `PERSON_1` and `PERSON_2` without learning who they are.

**Two local detectors, one Vault** — CloakBot separates non-computable spans from numeric or temporal spans so it can both preserve task structure and keep enough normalized data locally for later math execution.

**Remote LLM as reasoning engine only for math** — math turns ask the remote model for structure in `<python_snippet_N>` blocks; the final numeric answer is computed locally against Vault values.

**Fail-open by default** — if the local vLLM server is unreachable, the current default is to pass the message through unchanged rather than block the turn. The sanitizer APIs also support strict fail-closed behavior.

**Streaming-safe post-processing** — the CLI buffers streamed output until math execution, restoration, and report rendering are finished. The user sees the finalized answer, not intermediate placeholders.

**Hook-based integration** — the privacy layer is largely isolated under `cloakbot/privacy/` and integrates into the main runtime through `pre_llm_hook` and `post_llm_hook` in [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574).

**Roadmap already scaffolded in code** — document intent, tool-output sanitization helpers, and tool-interceptor placeholders already exist, but they are not fully wired into the runtime yet.

---

## Hackathon Tracks

- **Main Track** — Gemma 4 Good: using Gemma 4 locally for privacy-preserving AI
- **Ollama Special Track** — local model inference (vLLM, compatible with Ollama API)

---

## Credits & License

CloakBot is built on [nanobot](https://github.com/HKUDS/nanobot) (MIT License) by HKUDS. The channel integrations, session management, memory system, and CLI come from the upstream framework. CloakBot's privacy-specific work in this repo lives primarily under `cloakbot/privacy/`, [vllm.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/providers/vllm.py:1), and the hook integration points in [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574).
