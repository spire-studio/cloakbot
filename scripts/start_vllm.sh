#!/usr/bin/env bash
# Start the vLLM server from the project virtualenv.
#
# First-time setup on the Ubuntu server:
#   sudo apt-get update
#   sudo apt-get install -y build-essential python3.12-dev
#   uv sync --extra vllm
#   uv pip install -U vllm --pre \
#     --extra-index-url https://wheels.vllm.ai/nightly/cu129 \
#     --extra-index-url https://download.pytorch.org/whl/cu129 \
#     --index-strategy unsafe-best-match
#   uv pip install transformers==5.5.0
#
# Then run this script:
#   bash scripts/start_vllm.sh
#
# Env overrides:
#   GEMMA_MODEL_ID   HuggingFace model ID (default: google/gemma-4-E2B-it)
#   VLLM_API_KEY     Bearer token clients must send (required)
#   VLLM_PORT        Port to listen on (default: 8000)
#   VLLM_DTYPE       Torch dtype: bfloat16 | float16 (default: bfloat16)
#   VLLM_MAX_LEN     Max context length in tokens (default: 8192)
#   VLLM_LIMIT_MM    Multimodal limits JSON (default: {"image":0,"audio":0})
#
# For LoRA adapter switching, add to the vllm serve call:
#   --enable-lora --lora-modules pii-lora=./adapters/pii

set -euo pipefail

# Load .env if present (same file Python reads)
if [[ -f .env ]]; then
    set -a && source .env && set +a
fi

MODEL="${VLLM_MODEL:-${GEMMA_MODEL_ID:-google/gemma-4-E2B-it}}"
PORT="${VLLM_PORT:-8000}"
DTYPE="${VLLM_DTYPE:-bfloat16}"
MAX_LEN="${VLLM_MAX_LEN:-8192}"
LIMIT_MM="${VLLM_LIMIT_MM:-{\"image\":0,\"audio\":0}}"

if [[ -z "${VLLM_API_KEY:-}" ]]; then
    echo "ERROR: VLLM_API_KEY is not set."
    echo "  export VLLM_API_KEY=your-secret-token"
    echo "  or copy .env.example to .env and fill it in."
    exit 1
fi

VLLM_BIN="${VLLM_BIN:-.venv/bin/vllm}"
if [[ ! -x "$VLLM_BIN" ]]; then
    VLLM_BIN="$(command -v vllm || true)"
fi
if [[ -z "$VLLM_BIN" ]]; then
    echo "ERROR: vllm executable not found."
    echo "  Run the setup commands above, or activate the venv before starting."
    exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERROR: python executable not found."
    exit 1
fi

PY_INCLUDE="$("$PYTHON_BIN" -c 'import sysconfig; print(sysconfig.get_path("include") or "")')"
PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ ! -f "$PY_INCLUDE/Python.h" ]]; then
    echo "ERROR: Python C headers not found at $PY_INCLUDE/Python.h"
    echo "  Install system build prerequisites, for example:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y build-essential python${PY_VERSION}-dev"
    exit 1
fi

echo "==> Starting vLLM server"
echo "    model   : $MODEL"
echo "    port    : $PORT"
echo "    dtype   : $DTYPE"
echo "    max_len : $MAX_LEN"
echo "    mm      : $LIMIT_MM"
echo "    vllm    : $VLLM_BIN"
echo ""

args=(
    serve "$MODEL"
    --host 0.0.0.0
    --port "$PORT"
    --api-key "$VLLM_API_KEY"
    --dtype "$DTYPE"
    --max-model-len "$MAX_LEN"
)

if [[ -n "$LIMIT_MM" ]]; then
    args+=(--limit-mm-per-prompt "$LIMIT_MM")
fi

env -u VLLM_BASE_URL -u VLLM_MODEL "$VLLM_BIN" "${args[@]}"
