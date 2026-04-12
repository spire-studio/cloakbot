# CloakBot — Privacy-Preserving AI Assistant

> Built on [nanobot](https://github.com/HKUDS/nanobot) · Submitted to the **Gemma 4 Good Hackathon** (Kaggle, May 2026)

CloakBot adds a **local, multi-agent privacy layer** between you and any remote LLM. Before your message leaves your device, a local Gemma 4 model detects and tokenizes personally identifiable information (PII) and sensitive business data — replacing them with typed, reversible placeholders. After the remote LLM responds, placeholders are restored so you read original values in the reply. For tasks like math computation and document analysis, sensitive data never leaves your device at all.

**Your data never reaches the cloud in its raw form.**

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
  └─► [Local Gemma 4 via vLLM]
        • Detect PII & sensitive entities (3 passes: input, output, tool results)
        • Replace with typed tokens  e.g. "Alice" → <<PERSON_1>>
        • Build session Vault (token ↔ raw mapping)
  └─► [Remote LLM — Claude / GPT / Gemini]
        • Receives sanitized prompt only
        • Responds referencing placeholders
        • For math/code tasks: returns reasoning + Python snippet only
  └─► [Local Post-Processing]
        • Scan LLM response for hallucinated PII (pass 2)
        • Execute any code locally with real values from Vault
        • Restore <<PERSON_1>> → "Alice"
        • Emit transparency report
  └─► User sees original values in the final reply
```

**Example — Chat**

```
You:        My name is Alice Chen, email alice@acme.com. What's my name?
🔒 Masked:  "Alice Chen" [PERSON, medium] → <<PERSON_1>>
            "alice@acme.com" [EMAIL, medium] → <<EMAIL_1>>
CloakBot:   Your name is Alice Chen.
📋 Report:  2 entities masked in input · 0 leaked in response · all restored ✓
```

**Example — Math**

```
You:        My salary is $142,500. What is 18% of it?
🔒 Masked:  "142500" [NUM, low] → <<NUM_1>> · "18" passes through
Sent:       "What is 18% of <<NUM_1>>? Give reasoning and a Python snippet."
Remote:     "Multiply <<NUM_1>> by 0.18. → result = NUM_1 * 0.18"
Local exec: result = 142500 * 0.18 = 25650.0
CloakBot:   18% of $142,500 is $25,650.00
📋 Report:  1 entity masked · computed locally · remote saw no real figure ✓
```

---

## What Gets Detected

| Category | Examples | Default Severity |
|---|---|---|
| Personal PII | Names, phone numbers, emails, addresses, national IDs | Medium |
| High-sensitivity PII | SSNs, credit card numbers, medical data, date of birth | High |
| Business-sensitive | Deal prices, financial figures, M&A targets, headcount, internal dates | High |
| Network identifiers | IP addresses, MAC addresses | Low |
| Quasi-identifiers | Combinations that reveal identity even if each item seems harmless | Medium |
| Numeric (context-sensitive) | Salaries, account balances, medical dosages | Low–High |

Detection is context-aware and bilingual (English + Chinese). Public figures and widely known companies in purely descriptive context are intentionally not redacted.

### Token Schema

All entities are replaced using the pattern `<<ENTITY_TYPE_INDEX>>`, producing consistent, readable tokens:

| Raw Value | Token | Severity |
|---|---|---|
| `Alice Chen` | `<<PERSON_1>>` | Medium |
| `alice@acme.com` | `<<EMAIL_1>>` | Medium |
| `555-123-4567` | `<<PHONE_1>>` | Medium |
| `123-45-6789` | `<<SSN_1>>` | High |
| `$142,500` | `<<NUM_1>>` | Low |
| `Stanford Hospital` | `<<ORG_1>>` | Medium |
| `Metformin 500mg` | `<<MEDICAL_1>>` | High |

Indexed per type so the remote LLM can still track relationships between entities (e.g. `PERSON_1` and `PERSON_2` are different people) without knowing who they are.

---

## Multi-Agent System Design

CloakBot uses a **hybrid multi-agent architecture**: a local Orchestrator coordinates parallel specialist agents, all running on Gemma 4. The remote LLM is treated as an untrusted compute resource — it only ever receives sanitized text.

### Trust Boundary

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LOCAL TRUST ZONE                             │
│                                                                     │
│   User ──► [ Input Gate ]                                           │
│                  │                                                  │
│                  ▼                                                  │
│         [ Orchestrator ]  ◄── session state & Vault                 │
│          /       |       \                                          │
│         ▼        ▼        ▼                                         │
│   [Detector]  [Classifier]  [Transparency Logger]                   │
│       │            │                                                │
│       ▼            ▼                                                │
│    [Handler] ──► [Vault]                                            │
│       │                                                             │
│       ▼                                                             │
│   [Task Router]                                                     │
│    /    |    \                                                      │
│   ▼     ▼     ▼                                                     │
│ [Chat] [Math] [Doc/Data]    ← local task agents                     │
│         │        │                                                  │
│         ▼        ▼                                                  │
│    [Local Executor]  (sandboxed Python + Gemma 4)                   │
│                                                                     │
└──────────────────┬──────────────────────────────────────────────────┘
                   │  sanitized payload only — never raw PII
   ────────────────┼──────────── REMOTE BOUNDARY ─────────────────────
                   ▼
            [ Remote LLM Proxy ]  (Claude / GPT / Gemini via litellm)
                   │
   ────────────────┼─────────────────────────────────────────────────
                   │  response re-enters local trust zone
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    POST-RESPONSE LOCAL PIPELINE                      │
│                                                                      │
│   [ Detector pass 2 ]  ← scan for hallucinated / leaked PII         │
│           │                                                          │
│   [ Tool Call Interceptor ]  ← if LLM requests tool use             │
│       /         \                                                    │
│  [Execute]   [Detector pass 3]  ← mandatory post-tool PII scan      │
│       \         /                                                    │
│      [Handler]  ← sanitize tool output before re-entry              │
│           │                                                          │
│      [ Restorer ]  ← swap tokens back using Vault                   │
│           │                                                          │
│   [ Transparency Report ]  ← show user what was masked              │
│           │                                                          │
└───────────┼──────────────────────────────────────────────────────────┘
            ▼
         Output → User ✓
```

### Agents

| Agent | Role | Model |
|---|---|---|
| **Orchestrator** | Routes by intent, manages session Vault lifetime, enforces trust boundary | Gemma 4 |
| **Detector** ×3 | NER over user input (pass 1), LLM response (pass 2), tool outputs (pass 3) | Gemma 4 + optional bert-base-NER fast path |
| **Classifier** | Assigns severity (HIGH / MEDIUM / LOW) to each entity | Gemma 4 |
| **Handler** | Applies Redact+Tokenize strategy, writes to Vault | Rule-based |
| **Vault** | Session-scoped token ↔ raw mapping; ephemeral by default | In-memory |
| **Task Router** | Detects task type (chat / math / doc) from sanitized input | Gemma 4 |
| **Math Agent** | Sends expression to remote for reasoning+snippet; executes locally | Local sandbox |
| **Doc/Data Agent** | Chunks docs, sanitizes per-chunk with shared Vault, aggregates results | Gemma 4 |
| **Tool Interceptor** | Wraps every tool call; forces Detector pass 3 on all tool outputs | Rule-based |
| **Restorer** | Reverse-lookup Vault to rehydrate final output | Rule-based |
| **Transparency Logger** | Produces per-turn privacy report for the user | Rule-based |

### Detector Passes (Defense in Depth)

The Detector runs **three times per turn**, not once:

```
Pass 1  user input        → prevent raw PII from leaving device
Pass 2  LLM response      → catch hallucinated or training-data PII
Pass 3  tool call output  → catch PII introduced by external tools (search, DB, APIs)
```

This triple-pass approach is CloakBot's core security guarantee: PII cannot leak in, cannot leak out, and cannot be injected by tools.

### Math Privacy (Goal 2)

For computation tasks, the remote LLM acts as a **reasoning engine only** — it never sees actual numbers:

```
Input:   "My salary is $142,500. What is 18% of it?"
Masked:  "What is 18% of <<NUM_1>>? Give reasoning + Python snippet."
Remote:  "Multiply by 0.18. → result = NUM_1 * 0.18"
Local:   result = 142500 * 0.18          # real value substituted from Vault
Output:  "$25,650.00"
```

### Document & Dataset Privacy (Goal 3)

For large documents and datasets, CloakBot uses a **chunk-map-aggregate** strategy:

**Documents (PDF, DOCX, TXT):**
1. Parse → extract text + structure (headings, tables, metadata)
2. Chunk into ~512-token segments, respecting sentence boundaries
3. Sanitize each chunk with a **shared Vault** (so `PERSON_1` is consistent across the whole document)
4. Send sanitized chunks to remote LLM for partial analysis
5. Local Aggregator merges partial analyses
6. Restorer pass on aggregated result

**Datasets (CSV, JSON, Parquet):**
1. Column-level PII classification first (PII / non-PII / mixed)
2. PII columns tokenized with consistent mapping (all `"Alice Chen"` → same `PERSON_1`)
3. Non-PII columns pass through unmodified
4. Remote LLM receives sanitized schema + sample only
5. Remote returns analysis plan or Python code
6. Local Executor runs analysis on real data; results sanitized before display

### Tool Call Privacy (Goal 4)

Tool outputs are an often-overlooked PII attack surface. CloakBot treats every tool result as untrusted:

```
LLM requests tool call (e.g. web_search, DB query, API call)
        │
[ Interceptor validates tool name & args ]
        │
[ Execute tool locally ]
        │
[ Detector pass 3 — mandatory, no bypass ]
        │
[ Handler sanitizes tool output ]
        │
[ Sanitized result returned to LLM loop ]
```

Example: `web_search("Alice Chen lawsuit")` returns public court records with SSNs and addresses → Interceptor detects and tokenizes before the LLM sees it again.

---

## Architecture

```
cloakbot/
├── cloakbot/
│   ├── sanitizer/               ← CloakBot's core contribution
│   │   ├── pii_detector.py          Gemma 4 NER via vLLM (3-pass)
│   │   ├── classifier.py            Entity severity classification
│   │   ├── handler.py               Redact+Tokenize strategy
│   │   ├── vault.py                 Session-scoped token ↔ raw Vault
│   │   ├── restorer.py              Reverse-lookup and rehydration
│   │   └── sanitize.py              Session-level mapping + rewrite/remap
│   ├── agents/
│   │   ├── orchestrator.py          Top-level coordinator
│   │   ├── task_router.py           Intent detection → chat/math/doc routing
│   │   ├── math_agent.py            Local execution of remote-generated snippets
│   │   ├── doc_agent.py             Chunk-map-aggregate for documents & datasets
│   │   └── tool_interceptor.py      Mandatory post-tool PII scanning
│   ├── providers/
│   │   └── vllm.py                  OpenAI-compatible client → local vLLM server
│   └── agent/
│       └── loop.py                  Sanitization middleware (2 hooks)
├── tests/
│   ├── sanitizer/                   Unit + integration tests
│   └── agents/                      Agent-level tests (mocked LLM)
└── scripts/
    ├── download_model.sh            One-time model download
    ├── start_vllm.sh                Start vLLM server
    └── test_sanitizer.py            Smoke test
```

Session-level placeholder mappings are persisted as JSON under `~/.cloakbot/sanitizer_maps/`, so the same entity always maps to the same placeholder across all turns in a conversation.

---

## Roadmap

### ✅ v0.1 — MVP (Current, April 2026)
- [x] Gemma 4 NER via vLLM for PII detection (pass 1 only)
- [x] Redact+Tokenize with `<<ENTITY_TYPE_N>>` schema
- [x] Session Vault with JSON persistence
- [x] Remote LLM proxy (Claude / GPT / Gemini via litellm)
- [x] Restorer for final output rehydration
- [x] Streaming-safe remap (buffer → remap → re-emit)
- [x] Basic math privacy: tokenize numerics, execute locally
- [x] Smoke tests with mocked vLLM

### 🔨 v0.2 — Multi-Pass Detection
- [ ] Detector pass 2: scan LLM response for hallucinated PII
- [ ] Detector pass 3: mandatory post-tool-call scan via Tool Interceptor
- [ ] Classifier agent: HIGH / MEDIUM / LOW severity per entity type
- [ ] Transparency Logger: per-turn privacy report shown to user
- [ ] Math Agent: full reasoning+snippet pipeline with local sandboxed execution
- [ ] Fail-open / fail-closed mode toggle per entity severity

### 🔭 v0.3 — Document & Dataset Privacy
- [ ] Doc Agent: chunk-map-aggregate pipeline for PDF, DOCX, TXT
- [ ] Dataset Agent: column-level PII classification for CSV, JSON, Parquet
- [ ] Shared Vault across chunks (consistent entity mapping per document)
- [ ] Local Aggregator for partial analysis results
- [ ] Orchestrator Agent: full Gemma 4 powered intent routing

### 🚀 v0.4 — Production Hardening 
- [ ] Encrypted Vault persistence option (for long-running doc sessions)
- [ ] bert-base-NER fast path for latency-sensitive detection
- [ ] Quasi-identifier combination detection
- [ ] Bilingual detection improvements (English + Chinese)
- [ ] Web UI with real-time transparency dashboard
- [ ] Policy engine: per-user or per-org entity handling rules
- [ ] Full integration test suite

---

## Setup

### 1. Clone & install

```bash
git clone <this-repo> cloakbot && cd cloakbot
curl -Ls https://astral.sh/uv/install.sh | sh   # install uv if needed
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
# Unit tests (no vLLM needed — all LLM calls are mocked)
uv run --extra dev pytest tests/sanitizer/ -v

# Agent tests (mocked LLM + Vault)
uv run --extra dev pytest tests/agents/ -v

# Integration tests (requires running vLLM server)
uv run --extra dev pytest tests/ -m integration -v
```

---

## Design Decisions

**Redact + Tokenize, not Pseudonymize** — `<<PERSON_1>>` is simpler and safer than replacing names with fake-but-realistic names. No fake-data consistency to manage, no risk of fake data colliding with real entities. The remote LLM can still track relationships between `PERSON_1` and `PERSON_2` without knowing who they are.

**Three Detector passes** — single-pass detection (input only) misses two major PII surfaces: LLM hallucinations (e.g. the model generates a real person's email from training data) and tool-injected PII (e.g. a web search returns court records with SSNs). CloakBot treats every data boundary as a detection checkpoint.

**Remote LLM as reasoning engine only** — for math and code tasks, the remote model provides algorithm and structure; local execution provides results. Sensitive values never travel to the cloud even as part of a computation.

**Shared Vault across document chunks** — when processing large documents, the same entity must always map to the same token. A shared Vault ensures `Alice Chen` is `PERSON_1` in chunk 1 and still `PERSON_1` in chunk 47.

**Fail-open by default** — if the local vLLM server is unreachable, messages pass through unmodified rather than blocking the user. Set `fail_open=False` in `loop.py` for strict mode, which will block all unverified messages.

**Streaming-safe remap** — the CLI streams tokens. When sanitization is active, the stream is buffered internally until the LLM finishes, then remapped and re-emitted. The user never sees raw placeholders.

**No nanobot core changes** — the sanitizer and agent layer are self-contained modules. Integration is two hooks in `loop.py` (one before the LLM call, one after). The feature can be disabled or removed without touching nanobot internals.

---

## Hackathon Tracks

- **Main Track** — Gemma 4 Good: using Gemma 4 locally for privacy-preserving AI
- **Ollama Special Track** — local model inference (vLLM, compatible with Ollama API)

---

## Credits & License

CloakBot is built on [nanobot](https://github.com/HKUDS/nanobot) (MIT License) by HKUDS. The channel integrations, session management, memory system, and CLI are from nanobot, used unchanged. CloakBot's contribution is entirely in `cloakbot/sanitizer/`, `cloakbot/agents/`, and the two hooks in `cloakbot/agent/loop.py`.

