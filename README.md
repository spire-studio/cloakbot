# CloakBot — Privacy-Preserving AI Assistant

> Built on [cloakbot](https://github.com/HKUDS/cloakbot) · Submitted to the **Gemma 4 Good Hackathon** (Kaggle, May 2026)

CloakBot adds a **local privacy layer** between you and any remote LLM. Before your message leaves your device, a local Gemma 4 model detects and redacts personally identifiable information (PII) and sensitive business data — replacing them with typed placeholders. After the remote LLM responds, the placeholders are restored, so you read the original names and values in the reply.

Your data never reaches the cloud in its raw form.

## How It Works

```
User message
  └─► [Local Gemma 4 E2B via vLLM]
        • Detect PII & sensitive entities
        • Replace with placeholders  e.g. "Alice" → {{PERSON_1}}
  └─► [Remote LLM — Claude / GPT]
        • Receives sanitized prompt
        • Responds referencing placeholders
  └─► [Local remap]
        • {{PERSON_1}} → "Alice"
        • User sees original names in the reply
```

**Example**

```
You:       My name is Alice Chen, email alice@acme.com. What's my name?
🔒 Redacted before sending to AI: "Alice Chen" [person], "alice@acme.com" [email]
CloakBot:  Your name is Alice Chen.
```

The remote LLM only ever sees `{{PERSON_1}}` and `{{EMAIL_1}}`.

## What Gets Detected

| Category | Examples |
|----------|---------|
| Personal PII | Names, phone numbers, emails, IDs, addresses, credentials |
| Business-sensitive | Deal prices, financial figures, M&A targets, internal dates, headcount |
| Quasi-identifiers | Combinations that reveal strategy even if each item seems harmless |

Detection is context-aware and bilingual (English + Chinese). Public figures and widely known companies in purely descriptive context are intentionally not redacted.

## Architecture

```
cloakbot/
├── cloakbot/
│   ├── sanitizer/          ← CloakBot's core contribution
│   │   ├── pii_detector.py     Gemma 4 NER via vLLM
│   │   └── sanitize.py         Session-level mapping + rewrite/remap
│   ├── providers/
│   │   └── vllm.py             OpenAI-compatible client → local vLLM server
│   └── agent/
│       └── loop.py             Sanitization middleware (2 hooks)
└── scripts/
    ├── download_model.sh   One-time model download
    ├── start_vllm.sh       Start vLLM server
    └── test_sanitizer.py   Smoke test
```

Session-level placeholder mappings are persisted as JSON under `~/.cloakbot/sanitizer_maps/`, so the same entity always maps to the same placeholder across all turns in a conversation.

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

Set up the remote LLM (Claude, GPT, etc.) in `~/.cloakbot/config.json` as usual for cloakbot.

### 3. Start the vLLM server (Ubuntu / GPU machine)

```bash
# First time: install vllm and authenticate with HuggingFace
uv sync --extra vllm
uv run huggingface-cli login          # accept Gemma license at hf.co/google/gemma-4-E2B-it

# Start server (reads VLLM_API_KEY and VLLM_MODEL from .env automatically)
bash scripts/start_vllm.sh
```

> The vLLM server exposes an OpenAI-compatible API. CloakBot's sanitizer uses it exclusively for detection — the remote LLM call is completely separate.

### 4. Verify the sanitizer

```bash
uv run python scripts/test_sanitizer.py
```

### 5. Chat

```bash
uv run python -m cloakbot agent --config ~/.cloakbot/config.json
```

## Running Tests

```bash
# Unit tests (no vLLM needed — all LLM calls are mocked)
uv run --extra dev pytest tests/sanitizer/ -v

# Integration tests (requires running vLLM server)
uv run --extra dev pytest tests/sanitizer/ -m integration -v
```

## Design Decisions

**Fail-open by default** — if the local vLLM server is unreachable, messages pass through unmodified rather than blocking the user. Set `fail_open=False` in `loop.py` for strict mode.

**Session-level mapping** — placeholder assignments persist across turns. The same entity always gets the same placeholder within a conversation, so the remapper can restore values mentioned in earlier turns.

**Streaming-safe remap** — the CLI streams tokens. When sanitization happens, the stream is buffered internally until the LLM finishes, then remapped and re-emitted. The user never sees raw placeholders.

**No cloakbot core changes** — the sanitizer is a self-contained module. Integration is two hooks in `loop.py` (one before the LLM call, one after). Easy to remove or disable.

## Hackathon Tracks

- **Main Track** — Gemma 4 Good: using Gemma 4 for privacy-preserving AI
- **Ollama Special Track** — local model inference (vLLM, compatible with Ollama)

## Credits

Built on [cloakbot](https://github.com/HKUDS/cloakbot) (MIT license) by HKUDS. The channel integrations, session management, memory system, and CLI are from cloakbot unchanged. CloakBot's contribution is entirely in `cloakbot/sanitizer/` and the two hooks in `cloakbot/agent/loop.py`.

## License

MIT
