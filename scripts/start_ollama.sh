#!/usr/bin/env bash
# Start Ollama as the local Gemma 4 E2B backend for CloakBot.
#
# Why Ollama: ships the model + an OpenAI-compatible endpoint in one tool —
# no GGUF wrangling, no per-OS Metal/CUDA forks. Runs on a 2019 MacBook Air.
# This is the path we recommend for real-world adoption (vLLM stays for fast
# reproducible evals on a GPU machine).
#
# Prerequisites (one-time):
#   macOS / Linux: curl -fsSL https://ollama.com/install.sh | sh
#   Windows:        https://ollama.com/download/windows
#
# What this script does:
#   1. Starts the Ollama daemon (if not already running)
#   2. Pulls Gemma 4 E2B (~5 GB) on first run
#   3. Warms the model with a single inference (avoids first-token latency)
#
# After this script:
#   - Ollama listens on http://127.0.0.1:11434
#   - OpenAI-compatible endpoint at http://127.0.0.1:11434/v1
#   - Point CloakBot at it via .env:
#       GEMMA_BASE_URL=http://127.0.0.1:11434/v1
#       GEMMA_API_KEY=ollama        # Ollama doesn't enforce auth; any value works
#       GEMMA_MODEL=gemma4:e2b
#
# Env overrides:
#   OLLAMA_MODEL  Model tag (default: gemma4:e2b)
#                 Check `ollama search gemma` if this tag doesn't pull.
#   OLLAMA_HOST   Bind address (default: 127.0.0.1:11434)

set -euo pipefail

MODEL="${OLLAMA_MODEL:-gemma4:e2b}"
HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

if ! command -v ollama >/dev/null 2>&1; then
    echo "ERROR: ollama is not installed."
    echo "  macOS / Linux: curl -fsSL https://ollama.com/install.sh | sh"
    echo "  Windows:       https://ollama.com/download/windows"
    exit 1
fi

if curl -fsS "http://${HOST}/api/tags" >/dev/null 2>&1; then
    echo "==> Ollama daemon already running on ${HOST}"
else
    echo "==> Starting Ollama daemon on ${HOST}"
    OLLAMA_HOST="$HOST" ollama serve >/tmp/ollama.log 2>&1 &
    # Wait up to ~10s for the daemon to come up
    for _ in $(seq 1 20); do
        if curl -fsS "http://${HOST}/api/tags" >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    if ! curl -fsS "http://${HOST}/api/tags" >/dev/null 2>&1; then
        echo "ERROR: Ollama daemon failed to start. Tail of /tmp/ollama.log:"
        tail -20 /tmp/ollama.log 2>/dev/null || true
        exit 1
    fi
fi

if OLLAMA_HOST="$HOST" ollama list | awk 'NR>1{print $1}' | grep -qx "$MODEL"; then
    echo "==> Model ${MODEL} already pulled"
else
    echo "==> Pulling ${MODEL} (~5 GB; typically 3-5 min on broadband — feel free to keep working in another terminal)"
    OLLAMA_HOST="$HOST" ollama pull "$MODEL"
fi

echo "==> Warming ${MODEL}"
OLLAMA_HOST="$HOST" ollama run "$MODEL" "Reply with the single word OK." </dev/null \
    | head -c 64 >/dev/null && echo "    ready."

cat <<EOF

✅ Ollama is ready.

   Endpoint: http://${HOST}/v1
   Model:    ${MODEL}

Add to .env (or uncomment the Ollama profile in .env.example):

   GEMMA_BASE_URL=http://${HOST}/v1
   GEMMA_API_KEY=ollama
   GEMMA_MODEL=${MODEL}

CloakBot uses one OpenAI-compatible client for both vLLM and Ollama —
same three GEMMA_* variables work for either backend.
EOF
