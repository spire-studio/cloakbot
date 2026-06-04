<p align="center">
  <img src=".github/assets/cloakbot-logo.png" alt="CloakBot" width="420" />
</p>

<h1 align="center">CloakBot — A Local Privacy Kernel for Frontier LLMs</h1>

<p align="center">Use Claude / GPT / Gemini without your data ever leaving your laptop.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Privacy-Pre--wire%20Enforcement-0F172A?style=flat-square" alt="Pre-wire Enforcement" />
  <img src="https://img.shields.io/badge/Gemma%204-Local%20Trust%20Layer-0F9D58?style=flat-square" alt="Gemma 4 Trust Layer" />
  <img src="https://img.shields.io/badge/Remote%20LLM-Claude%20%7C%20GPT%20%7C%20Gemini-8B5CF6?style=flat-square" alt="Remote LLM Claude GPT Gemini" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A?style=flat-square" alt="MIT License" />
</p>

<p align="center"><strong>English</strong> | <a href="README.zh-CN.md">简体中文</a></p>

<p align="center"><sub>Built on <a href="https://github.com/HKUDS/nanobot">nanobot</a> · Submitted to the <strong>Gemma 4 Good Hackathon</strong> (Kaggle, May 2026)</sub></p>

---

## 📋 TL;DR

Frontier LLM use is now load-bearing — but the data that crosses the wire is non-revocable. CloakBot moves enforcement **before the wire**: a local privacy kernel on **Gemma 4 E2B** that detects sensitive spans, assigns stable typed placeholders, redacts images, chunks long documents, and restores outputs locally from a per-session vault. The remote LLM is interchangeable — Claude, GPT, and Gemini all accept the sanitised stream unchanged.

> **2,872 entity-test instances of receipts** across three leak-eval layers — `7.98%` pair leak (text) · `1.11%` span leak (visual) · `6.26%` pair leak (long-document) · `97.14%` cross-turn alias consistency.

---

## 🔍 How it works

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

Detection is split into `GeneralPrivacyDetector` (non-computable text spans) and `DigitPrivacyDetector` (numeric/temporal values normalised for later local math). Each span becomes an indexed token — `<<ENTITY_TYPE_INDEX>>` — so the remote LLM can still track relationships (`PERSON_1` ≠ `PERSON_2`) without knowing who they are: e.g. `Alice Chen → <<PERSON_1>>`, `555-123-4567 → <<PHONE_1>>`, `$142,500 → <<FINANCE_1>>`, `Metformin 500mg → <<MEDICAL_1>>`.

---

## Why a small LLM, not regex or BERT-NER?

**TL;DR — regex catches the easy 20%; the other 80% needs context.** CloakBot uses both: regex on the fast path (emails, invoice numbers, transaction IDs, file paths — in [`privacy/core/detection/`](cloakbot/privacy/core/detection/)), and Gemma 4 E2B for everything regex and BERT-NER cannot do.

| Failure mode | Regex | BERT-NER (Presidio, spaCy) | **Gemma 4 E2B** |
|---|:---:|:---:|:---:|
| Known formats — email, SSN, credit card | ✓ | ✓ | ✓ |
| Disambiguate `"John"` as a placeholder vs a real customer | ✗ | ✗ | ✓ |
| Instructional numbers — *"give me 3 bullet points about Q4 earnings"* | tokenizes `3` (breaks the request) | varies by tag set | ✓ kept as task structure |
| Combination identifiers — *"67-year-old male diabetic in ZIP 90210"* | ✗ | ✗ | ✓ |
| Cross-turn entity disambiguation — *"someone else surnamed Lin"* ≠ existing `<<PERSON_1>>` Lin Zhiyuan | n/a | n/a | ✓ emits `new` |
| Indirect identifiers — *"the patient I mentioned earlier"* | ✗ | ✗ | ✓ |
| User-defined entities — *"also redact our codename Falcon"* | edit regex | retrain | edit prompt |
| Domain shift — chat logs vs news-trained NER | n/a | recall drops 20–40% | resilient |
| Multilingual (CN / JP / KR / EN) on one model | one regex set per locale | 600 MB+ per language | one 2B model |
| Computable normalization — `$1,200.50` → `1200.5` (ready for local math) | string-only | string-only | ✓ typed numeric |

A PII proxy that only catches the easy stuff is **strictly worse than no proxy** — users trust it. The real bar is reasoning about whether a token should be redacted *in this specific conversation*, a generative-LLM-shaped problem. Gemma 4 E2B is the one commercially-redistributable model that fits consumer hardware (~5 GB quantised, runs on a MacBook via Ollama), returns parseable JSON at T=0, and is multimodal and multilingual in one weight set — **the trust layer is the model**, not a chat rewriter bolted onto Presidio. The honest cost: ~50–200 ms per detector call vs regex's <1 ms, mitigated by concurrent general+digit detectors, regex on the fast path, and per-chunk concurrency. Full rationale, latency, and methodology in the [hackathon writeup](docs/HACKATHON_WRITEUP.md).

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

| Component | Role | Backend |
|---|---|---|
| `PrivacyRuntime` | Per-turn coordinator: sanitise, route, restore, audit | Python |
| `PiiDetector` | General + digit + intent detectors run concurrently, then deduplicated | Gemma 4 E2B |
| `ToolPrivacyInterceptor` (+ `chunking/`) | Tool I/O restoration, severity-gated approval, output sanitisation; long-document content-aware chunkers with cross-chunk vault coalesce | Gemma 4 E2B + rules |
| `VisualPrivacyPipeline` | OCR + bbox redaction + placeholder overlay + cross-modal recall bridge | Gemma 4 E2B + Pillow + Tesseract |
| `Session Vault` | Audit-traceable placeholder ↔ raw mapping with cross-turn alias reuse | JSON on disk |
| `Math Executor` | Local execution of remote-generated `<python_snippet_N>` blocks; AST-validated, arithmetic-only | Python AST sandbox |

Full component list and file tree in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 📊 Evals — trust by measurement

We refused to ship trust-by-assertion. Three end-to-end leak eval layers run against the **production pipeline** and answer one question per run: *did any ground-truth identifying token reach the upstream payload?*

| Layer | Coverage | Headline | Cross-turn alias |
|---|---|---|---:|
| **A1 — text input** | 4 domains × 20 sessions × 902 entity-turn pairs | **7.98%** pair leak · **5.88%** token leak | **97.14%** |
| **A2 — visual** | 10 invoice seeds × 180 PII spans × 197 redaction boxes | **1.11%** span leak · **1.01%** token leak | n/a |
| **A3 — long-document** | 3 domains × 20 sessions × 1,790 pairs via chunker | **6.26%** pair leak · **6.63%** token leak | **93.86%** |

- **100% pair recall** cross-domain on `EMAIL · PHONE · FINANCE · IP · URL`
- **MEDICAL recall: 20% → 95%** via type-driven prompt iteration (rules → adjacent examples)
- **0 of 226** A3 seam leaks fall within the 300-char chunker overlap band — every long-doc leak is an intra-chunk detector miss, not a boundary failure

Full per-template breakdown, methodology, and self-caught eval bugs in [`docs/HACKATHON_WRITEUP.md`](docs/HACKATHON_WRITEUP.md). Reproducibility: one command per layer in `tests/eval/runners/`.

> *All p95 latency numbers measured with Gemma 4 E2B served via vLLM on an RTX 5090. The MacBook (Ollama) path is functionally end-to-end but slower — MacBook is the target hardware, not the measurement rig.*

---

## 🛠️ Setup

### Fastest path — one command

```bash
# One-time: install Ollama + Node ≥24 + deps
curl -fsSL https://ollama.com/install.sh | sh
uv sync && cd webui && npm install && cd ..

bash scripts/quickstart_demo.sh
```

Starts Ollama with `gemma4:e2b`, bootstraps `.env`, launches the WebUI (gateway `:8000`, frontend `:5173`), and opens your browser. Drag [`docs/demo/demo_onboarding_memo.md`](docs/demo/demo_onboarding_memo.md) into the Composer to watch 20 PII entities masked end-to-end — click **Diff** on any bubble for the Local↔Remote view.

### Manual setup

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync
cd webui && npm install && cd ..        # WebUI frontend needs Node ≥24
cp .env.example .env                     # two profiles inside — pick ONE
```

Configure the remote LLM (Claude / GPT / Gemini) with `uv run python -m cloakbot onboard` (or edit `~/.cloakbot/config.json`), then start the local Gemma 4 backend — **pick one**:

**Option A — vLLM (GPU machine):** fast, reproducible; the path behind the A1/A2/A3 evals.

```bash
uv sync --extra vllm
uv run huggingface-cli login            # accept the Gemma license at hf.co/google/gemma-4-E2B-it
bash scripts/start_vllm.sh
```

**Option B — Ollama (macOS / Linux / WSL):** no GPU; the recommended real-world path.

```bash
bash scripts/start_ollama.sh            # pulls gemma4:e2b (~5 GB), warms the model
# then in .env:
#   GEMMA_BASE_URL=http://127.0.0.1:11434/v1
#   GEMMA_API_KEY=ollama        # Ollama doesn't enforce auth; any value works
#   GEMMA_MODEL=gemma4:e2b
```

Both backends expose the same OpenAI-compatible surface, used **only** for local PII detection — the remote LLM call is entirely separate. Then launch the WebUI:

```bash
uv run python -m cloakbot webui        # gateway :8000 · frontend :5173
```

---

## 🗺️ Roadmap

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

- **Domain-specific LoRA adapters** — fine-tune Gemma 4 E2B on vertical corpora (healthcare, legal, finance) to lift recall on domain-specific phrases. The same kernel, three adapters: pick by tenant.
- **ORG short / hyphenated name recall** (71.67% → 90% target) — the largest remaining A1 gap, addressable with the LoRA path above
- **Bilingual coverage** — Chinese-language eval templates + zh-CN detector prompt iteration
- **Streaming + per-turn batching** — Medical p95 6.2 s → < 2 s target
- **Encrypted Vault persistence** option for shared-machine deployments
- **Policy-driven severity tiers** beyond the current registry defaults (all `high` today)
- **Dataset / table-specific structured chunker** (CSV / Parquet) for analytics tool outputs

---

## Hackathon tracks

- **Main Track — Gemma 4 Good (Safety & Trust direction)** — Gemma 4 E2B as a local privacy kernel that enforces a pre-wire boundary before any byte reaches the remote LLM. Backed by 2,872 entity-test instances across A1 (text), A2 (visual), and A3 (long-document) leak evals — see [`docs/HACKATHON_WRITEUP.md`](docs/HACKATHON_WRITEUP.md).
- **Ollama Special Technology** — `bash scripts/start_ollama.sh` ships the model + the OpenAI-compatible endpoint in one tool. **Gemma 4 is the trust layer; Ollama is the deployment layer.** Try it: `bash scripts/quickstart_demo.sh`.

---

## ⭐ Star History

<a href="https://www.star-history.com/?repos=spire-studio%2Fcloakbot&type=date&logscale=&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=spire-studio/cloakbot&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=spire-studio/cloakbot&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=spire-studio/cloakbot&type=date&legend=top-left" />
 </picture>
</a>

---

## Credits & license

CloakBot is built on [nanobot](https://github.com/HKUDS/nanobot) (MIT License) by HKUDS. The channel integrations, session management, memory system, and CLI come from the upstream framework. CloakBot's privacy-specific work lives primarily under [`cloakbot/privacy/`](cloakbot/privacy/), [`cloakbot/providers/vllm.py`](cloakbot/providers/vllm.py), and the hook integration points in [`cloakbot/agent/loop.py`](cloakbot/agent/loop.py).

Architecture, reliability, security, privacy-domain notes, and [design decisions](docs/design-docs/design-decisions.md) live under [`docs/`](docs/) — start with [`AGENTS.md`](AGENTS.md).

MIT License — see [`LICENSE`](LICENSE).
