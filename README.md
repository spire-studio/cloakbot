<p align="center">
  <img src="logo+cloakbot-readme.png" alt="CloakBot" width="420" />
</p>

<h1 align="center">CloakBot — A Local Privacy Kernel for Frontier LLMs</h1>

<p align="center">Use Claude / GPT / Gemini without your data ever leaving your laptop.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Privacy-Pre--wire%20Enforcement-0F172A?style=flat-square" alt="Pre-wire Enforcement" />
  <img src="https://img.shields.io/badge/Gemma%204-Local%20Trust%20Layer-0F9D58?style=flat-square" alt="Gemma 4 Trust Layer" />
  <img src="https://img.shields.io/badge/vLLM%20%2F%20Ollama-OpenAI%20Compatible-1F6FEB?style=flat-square" alt="vLLM / Ollama OpenAI Compatible" />
  <img src="https://img.shields.io/badge/Multi--Agent-6%20local%20components-7C3AED?style=flat-square" alt="Multi-Agent 6 local components" />
  <img src="https://img.shields.io/badge/Remote%20LLM-Claude%20%7C%20GPT%20%7C%20Gemini-8B5CF6?style=flat-square" alt="Remote LLM Claude GPT Gemini" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A?style=flat-square" alt="MIT License" />
</p>

<p align="center"><strong>English</strong> | <a href="README.zh-CN.md">简体中文</a></p>

<p align="center"><sub>Built on <a href="https://github.com/HKUDS/nanobot">nanobot</a> · Submitted to the <strong>Gemma 4 Good Hackathon</strong> (Kaggle, May 2026)</sub></p>

---

## TL;DR

Frontier LLM use is now load-bearing — but the data that crosses the wire is non-revocable. CloakBot moves enforcement **before the wire**: a local privacy kernel on **Gemma 4 E2B** that detects sensitive spans, assigns stable typed placeholders, redacts images, chunks long documents, and restores outputs locally from a per-session vault. The remote LLM is interchangeable — Claude, GPT, and Gemini all accept the sanitised stream unchanged.

> **2,872 entity-test instances of receipts** across three leak-eval layers — `7.98%` pair leak (text) · `1.11%` span leak (visual) · `6.26%` pair leak (long-document) · `97.14%` cross-turn alias consistency.

---

## Try it in 60 seconds

```bash
# One-time:  curl -fsSL https://ollama.com/install.sh | sh
# One-time:  Node ≥24 for the WebUI frontend  (nvm install 24  or  brew install node@24)
# One-time:  uv sync && cd webui && npm install && cd ..

bash scripts/quickstart_demo.sh
```

Starts Ollama with `gemma4:e2b`, bootstraps `.env`, launches the WebUI (gateway `:8000`, frontend `:5173`), and opens your browser. Drag [`docs/demo/demo_onboarding_memo.md`](docs/demo/demo_onboarding_memo.md) into the Composer to see 20 PII entities replaced with typed placeholders end-to-end, and click **Diff** on any bubble for the Local↔Remote view.

For a fuller setup (vLLM on a GPU machine, model download, custom config), see [§ Setup](#setup) below.

---

## Table of Contents

- [How it works](#how-it-works)
- [What gets detected](#what-gets-detected)
- [Why a small LLM, not regex or BERT-NER?](#why-a-small-llm-not-regex-or-bert-ner)
- [Multi-agent architecture](#multi-agent-architecture)
- [Evals — trust by measurement](#evals--trust-by-measurement)
- [Setup](#setup)
- [Roadmap](#roadmap)
- [Design decisions](#design-decisions)
- [Hackathon tracks](#hackathon-tracks)
- [Credits & license](#credits--license)

---

## How it works

```
User message (text + optional images / documents)
  └─► [ pre_llm_hook → PrivacyRuntime ]
        • Local Gemma 4 E2B detectors run concurrently (general + digit)
        • Images → OCR + visual bbox redaction + placeholder overlay
        • Long documents → content-aware chunker + per-chunk detection + vault coalesce
        • Tool I/O → severity-gated approval for non-local tools
        • Sensitive spans rewritten into <<TYPE_N>> placeholders, stored in the per-session Vault
  └─► [ Remote LLM ]   (Claude / GPT / Gemini — sanitised payload only)
        • Math turns: remote model emits <python_snippet_N>; real arithmetic happens locally
        • Tool calls: arguments restored locally, outputs re-sanitised before reuse
  └─► [ post_llm_hook → local restoration ]
        • Placeholder restoration via vault map
        • Per-turn transparency report
  └─► User sees original values in the final reply
```

Streaming output is buffered until restoration completes — the user never sees raw placeholders.

---

## What gets detected

| Category | Examples | Severity |
|---|---|:---:|
| Personal & contact | Names, phone, email, address | High |
| Unique identifiers | SSN, passport, account, license plate | High |
| Secrets & access | Passwords, API keys, tokens, private URLs | High |
| Organisation & network | Company names, school names, IPs | High |
| Medical & narrative | PHI, treatments, diagnoses, code names | High |
| Numeric & temporal | Money, dates, percentages, counts, measurements, coordinates | High |

The detector is split into `GeneralPrivacyDetector` (non-computable text spans) and `DigitPrivacyDetector` (numeric/temporal values normalised for later local math).

### Token schema

`<<ENTITY_TYPE_INDEX>>` — indexed per type so the remote LLM can still track relationships (e.g. `PERSON_1` and `PERSON_2` are different people) without knowing who they are.

| Raw | Token |
|---|---|
| `Alice Chen` | `<<PERSON_1>>` |
| `alice@acme.com` | `<<EMAIL_1>>` |
| `555-123-4567` | `<<PHONE_1>>` |
| `123-45-6789` | `<<ID_1>>` |
| `$142,500` | `<<FINANCE_1>>` |
| `December 15, 2026` | `<<DATE_1>>` |
| `Metformin 500mg` | `<<MEDICAL_1>>` |

---

## Why a small LLM, not regex or BERT-NER?

**TL;DR — regex catches the easy 20%; the other 80% needs context.** CloakBot uses both: regex on the fast path (emails, invoice numbers, transaction IDs, file paths — hand-rolled in [`privacy/core/detection/`](cloakbot/privacy/core/detection/) and [`visual_redaction.py`](cloakbot/privacy/visual_redaction.py)), and Gemma 4 E2B for everything regex and BERT-NER cannot do.

### What regex and BERT-NER cannot do

| Failure mode | Regex | BERT-NER (Presidio, spaCy) | **Gemma 4 E2B** |
|---|:---:|:---:|:---:|
| Known formats — email, SSN, credit card | ✓ | ✓ | ✓ |
| Disambiguate `"John"` as a placeholder vs a real customer | ✗ | ✗ | ✓ |
| Combination identifiers — *"67-year-old male diabetic in ZIP 90210"* | ✗ | ✗ | ✓ |
| User-defined entities — *"also redact our project codename Falcon"* | edit regex | retrain | edit prompt |
| Domain shift — chat logs vs the news corpora NER was trained on | n/a | recall drops 20–40% | resilient |
| Multilingual (CN / JP / KR / EN) on one model | one regex set per locale | 600 MB+ per language | one 2B model |
| Indirect identifiers — *"the patient I mentioned earlier"* | ✗ | ✗ | ✓ |

### Why the failure modes matter

A Presidio-style stack ships a *PII proxy that catches the easy stuff* — and that is **strictly worse than no proxy**, because users trust it. The bar for moving enforcement *before* the wire isn't pattern-matching; it's reasoning about whether a token should be redacted **in this specific conversation**. That's a generative-LLM-shaped problem.

### Why Gemma 4 E2B specifically

Gemma 4 E2B is the only commercially-redistributable model that simultaneously:

1. **Fits on consumer hardware** — 2B parameters, ~5 GB quantised, runs on a MacBook through Ollama.
2. **Returns parseable JSON at T=0** — span-level entity extraction without a fine-tune.
3. **Multimodal in one weight set** — same model handles OCR-extracted text and direct image reasoning.
4. **Speaks the languages CloakBot's users do** — Gemma 4 is multilingual out of the box; no per-locale model swap.
5. **Has a commercial license** — clinics, banks, and law firms can deploy it without a per-seat fee.

> **This is also a Gemma 4 hackathon.** A Presidio + BERT pipeline that uses Gemma as a chat rewriter would not be a meaningful demonstration of what Gemma can do. CloakBot puts Gemma where the trust decision actually happens — **the trust layer is the model**.

### The honest trade-off

Gemma is ~50–200 ms per detector call (measured on an RTX 5090 via vLLM) vs. regex's <1 ms. CloakBot mitigates this by (a) running general + digit detectors concurrently, (b) keeping regex on the fast path for known formats, (c) per-chunk concurrency for long documents. End result: HR p95 ~0.9 s, medical p95 ~6 s on entity-dense turns (see [Evals](#evals--trust-by-measurement)). The MacBook (Ollama) deployment path runs end-to-end but slower. Streaming + per-turn batching is the next milestone.

---

## Multi-agent architecture

```
┌─────────────────────────────── LOCAL TRUST ZONE ─────────────────────────────┐
│                                                                              │
│   User input  ──►  [ pre_llm_hook ]  ──►  [ PrivacyRuntime ]                 │
│                                                  │                           │
│           ┌──────────────────┬───────────────────┼─────────────────┐         │
│           ▼                  ▼                   ▼                 ▼         │
│      PiiDetector       ToolPrivacy        VisualPrivacy        DocChunker    │
│   (general + digit)    Interceptor          Pipeline          (long docs)    │
│           │            (tool I/O)        (OCR + bbox)              │         │
│           └──────────────────┬───────────────────────┬─────────────┘         │
│                              ▼                       ▼                       │
│                  [ Session Vault ]         [ Local Math Executor ]           │
│              (placeholder ↔ raw map,         (arithmetic-only AST,           │
│               per-session, on disk)            sandboxed)                    │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │  sanitised payload only
   ────────────────────────────────┼─────────── REMOTE BOUNDARY ───────────────
                                   ▼
                          [ Remote LLM ]   (Claude / GPT / Gemini)
                                   │  response re-enters local zone
   ────────────────────────────────┼───────────────────────────────────────────
                                   ▼
                         [ post_llm_hook ]  →  restore + per-turn report  →  User
```

### Components

| Component | Role | Backend |
|---|---|---|
| `PrivacyRuntime` | Per-turn coordinator: sanitise, route, restore, audit | Python |
| `PiiDetector` | General + digit + intent detectors run concurrently, then deduplicated | Gemma 4 E2B |
| `IntentAnalyzer` | Classifies turns as `chat` or `math` | Gemma 4 E2B |
| `ToolPrivacyInterceptor` | Tool I/O restoration; severity-gated approval; output sanitisation (incl. `read_file` / web_fetch / MCP) | Rule-based + detector |
| `ToolPrivacyDetector` + `chunking/` | Long-document path: content-aware chunkers (plaintext / JSON / HTML / Markdown), per-chunk concurrency + timeout, cross-chunk vault coalesce, fail-closed | Gemma 4 E2B |
| `VisualPrivacyPipeline` | OCR + bbox redaction + placeholder text rendered *inside* each black bar + cross-modal recall bridge (text-side entities forwarded as visual needles) | Gemma 4 E2B + Pillow + Tesseract |
| `process_user_document` | WebUI document upload (text/plain, text/markdown ≤ 64 KB) routed through the same chunker-backed sanitizer | Gemma 4 E2B |
| `Session Vault` | Audit-traceable placeholder ↔ raw mapping with cross-turn alias reuse (PERSON + ORG substring, NFKC-normalised) | JSON on disk |
| `Math Executor` | Local execution of remote-generated `<python_snippet_N>` blocks; AST-validated, arithmetic-only | Python AST sandbox |
| `Transparency Report` | Per-turn markdown summary of masked entities | Rule-based |

For the full file tree see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Evals — trust by measurement

We refused to ship trust-by-assertion. Three end-to-end leak eval layers run against the **production pipeline** and answer one question per run: *did any ground-truth identifying token reach the upstream payload?*

| Layer | Coverage | Headline | Cross-turn alias |
|---|---|---|---:|
| **A1 — text input** | 4 domains × 20 sessions × 902 entity-turn pairs | **7.98%** pair leak · **5.88%** token leak | **97.14%** |
| **A2 — visual** | 10 invoice seeds × 180 PII spans × 197 redaction boxes | **1.11%** span leak · **1.01%** token leak | n/a |
| **A3 — long-document** | 3 domains × 20 sessions × 1,790 pairs via chunker | **6.26%** pair leak · **6.63%** token leak | **93.86%** |

- **100% pair recall** cross-domain on `EMAIL · PHONE · FINANCE · IP · URL`
- **MEDICAL recall: 20% → 95%** via type-driven prompt iteration (rules → adjacent examples)
- **0 of 226** A3 seam leaks fall within the 300-char chunker overlap band — the boundary heuristic has perfect coverage; every long-doc leak is an intra-chunk detector miss

Full per-template breakdown, methodology, and self-caught eval bugs in [`docs/HACKATHON_WRITEUP_DRAFT.md`](docs/HACKATHON_WRITEUP_DRAFT.md). Reproducibility: one command per layer in `tests/eval/runners/`.

> *All p95 latency numbers measured with Gemma 4 E2B served via vLLM on an RTX 5090. The MacBook (Ollama) deployment path is functionally end-to-end but slower — MacBook is the target hardware, not the measurement rig.*

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync
# WebUI frontend requires Node ≥24 — `nvm install 24` or `brew install node@24`
cd webui && npm install && cd ..
```

### 2. Configure

```bash
cp .env.example .env
# Two profiles live in .env.example — pick ONE:
#   Profile A — vLLM on a GPU machine
#   Profile B — Ollama (no GPU required)
```

Set up the remote LLM (Claude, GPT, Gemini, etc.) in `~/.cloakbot/config.json` or run:

```bash
uv run python -m cloakbot onboard
```

### 3. Start the local Gemma 4 backend — pick ONE

CloakBot uses one OpenAI-compatible client for both backends, so the same three `GEMMA_*` variables in `.env` (`GEMMA_BASE_URL` / `GEMMA_API_KEY` / `GEMMA_MODEL`) work for either profile.

#### Option A: vLLM (Ubuntu / GPU machine) — fast, reproducible

```bash
uv sync --extra vllm
uv run huggingface-cli login          # accept Gemma license at hf.co/google/gemma-4-E2B-it
bash scripts/start_vllm.sh             # reads GEMMA_API_KEY / GEMMA_MODEL from .env
```

This is the path we use to produce the A1 / A2 / A3 eval reports.

#### Option B: Ollama (macOS / Linux / WSL) — no GPU required

```bash
# One-time: curl -fsSL https://ollama.com/install.sh | sh
bash scripts/start_ollama.sh
```

Pulls `gemma4:e2b` (~5 GB), starts the daemon, warms the model. Then in `.env`:

```
GEMMA_BASE_URL=http://127.0.0.1:11434/v1
GEMMA_API_KEY=ollama        # Ollama doesn't enforce auth; any value works
GEMMA_MODEL=gemma4:e2b
```

This is the path we recommend for real-world adoption — the privacy kernel runs on a MacBook.

> Either backend exposes the same OpenAI-compatible surface. CloakBot's sanitiser uses it exclusively for PII detection — the remote LLM call (Claude / GPT / Gemini) is completely separate.

### 4. Start the WebUI

```bash
uv run python -m cloakbot webui
# Gateway   http://127.0.0.1:8000
# Frontend  http://127.0.0.1:5173
```

Or use `bash scripts/quickstart_demo.sh` to do everything in one step.

---

## Roadmap

### ✅ Shipped (April – May 2026)

**Core privacy runtime (v0.1)** — April
- Split local detectors (general + digit) via Gemma 4 E2B
- Session Vault with JSON persistence + cross-turn alias reuse
- Math snippet contract + local AST-validated arithmetic executor
- IntentAnalyzer + chat/math routing
- `ToolPrivacyInterceptor` for tool I/O sanitisation + severity-gated approval

**Trust boundary expansion (v0.2)** — May
- ✓ Long-document chunker path (`ToolPrivacyDetector` + 4 content-aware chunkers: plaintext / JSON / HTML / Markdown)
- ✓ Visual pipeline: OCR + bbox redaction + placeholder overlay + cross-modal recall bridge
- ✓ WebUI document upload (text/plain, text/markdown ≤ 64 KB) via the same chunker-backed sanitizer
- ✓ Local↔Remote diff dialog with per-document entity highlighting
- ✓ Ollama as a first-class backend (no GPU required) + one-command demo launcher

**Trust by measurement (v0.3)** — May
- ✓ End-to-end leak eval harness (`tests/eval/runners/`)
- ✓ A1 / A2 / A3 layers — **2,872 entity-test instances** of receipts
- ✓ Type-driven detector prompts (MEDICAL recall 20% → 95%)
- ✓ Self-caught eval bugs surfaced and fixed (token-level scoring; full-value appearance tightening)

### 🚀 Future

- **Domain-specific LoRA adapters** — fine-tune Gemma 4 E2B on vertical corpora (healthcare, legal, finance) to lift recall on domain-specific phrases (e.g. `stage 2 chronic kidney disease`, short ORG names like `Turner Ltd`) and unlock policy-aware vertical deployments. The same kernel, three adapters: pick by tenant.
- **ORG short / hyphenated name recall** (71.67% → 90% target) — the largest remaining A1 gap, addressable with the LoRA path above
- **Bilingual coverage** — Chinese-language eval templates + zh-CN detector prompt iteration
- **Streaming + per-turn batching** — Medical p95 6.2 s → < 2 s target by overlapping detector concurrency with token streaming
- **Encrypted Vault persistence** option for shared-machine deployments
- **Policy-driven severity tiers** beyond the current registry defaults (all `high` today)
- **Dataset / table-specific structured chunker** (CSV / Parquet) for analytics tool outputs

---

## Design decisions

**Redact + Tokenize, not Pseudonymize** — `<<PERSON_1>>` is simpler and safer than replacing names with fake-but-realistic names. The remote LLM can still track relationships between `PERSON_1` and `PERSON_2` without learning who they are.

**Two local detectors, one Vault** — CloakBot separates non-computable spans from numeric or temporal spans so it can both preserve task structure and keep enough normalised data locally for later math execution.

**Remote LLM as reasoning engine only for math** — math turns ask the remote model for structure in `<python_snippet_N>` blocks; the final numeric answer is computed locally against Vault values.

**Hook-based integration** — the privacy layer is largely isolated under `cloakbot/privacy/` and integrates into the main runtime through `pre_llm_hook` and `post_llm_hook`, so the upstream nanobot loop remains untouched.

**Documents are tool-sourced privacy data** — there is no separate document worker; the same chunker-backed sanitiser path serves `read_file`, `web_fetch`, MCP tool results, and WebUI document uploads. One trust boundary, one Vault.

---

## Hackathon tracks

- **Main Track — Gemma 4 Good (Safety & Trust direction)** — Gemma 4 E2B as a local privacy kernel that enforces a pre-wire boundary before any byte reaches the remote LLM. Backed by 2,872 entity-test instances of receipts across A1 (text), A2 (visual), and A3 (long-document) leak evals — see [`docs/HACKATHON_WRITEUP_DRAFT.md`](docs/HACKATHON_WRITEUP_DRAFT.md).
- **Ollama Special Technology** — `bash scripts/start_ollama.sh` ships the model + the OpenAI-compatible endpoint in one tool — no GGUF wrangling, no per-OS Metal/CUDA forks. **Gemma 4 is the trust layer; Ollama is the deployment layer.** Try it: `bash scripts/quickstart_demo.sh`.

---

## Credits & license

CloakBot is built on [nanobot](https://github.com/HKUDS/nanobot) (MIT License) by HKUDS. The channel integrations, session management, memory system, and CLI come from the upstream framework. CloakBot's privacy-specific work in this repo lives primarily under [`cloakbot/privacy/`](cloakbot/privacy/), [`cloakbot/providers/vllm.py`](cloakbot/providers/vllm.py), and the hook integration points in [`cloakbot/agent/loop.py`](cloakbot/agent/loop.py).

Agent-oriented architecture, reliability, security, and privacy-domain notes live under [`docs/`](docs/) — start with [`AGENTS.md`](AGENTS.md).

MIT License — see [`LICENSE`](LICENSE).
