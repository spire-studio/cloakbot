#!/usr/bin/env bash
# Start the vLLM server using uv.
#
# First-time setup on the Ubuntu server:
#   uv sync --extra vllm
#
# Then run this script (or just run it — uv sync is idempotent):
#   bash scripts/start_vllm.sh
#
# Env overrides:
#   GEMMA_MODEL_ID   HuggingFace model ID (default: google/gemma-4-e2b-it)
#   VLLM_API_KEY     Bearer token clients must send (required)
#   VLLM_PORT        Port to listen on (default: 8000)
#   VLLM_DTYPE       Torch dtype: bfloat16 | float16 (default: bfloat16)
#   VLLM_MAX_LEN     Max context length in tokens (default: 8192)
#
# For LoRA adapter switching, add to the vllm serve call:
#   --enable-lora --lora-modules pii-lora=./adapters/pii

set -euo pipefail

# Load .env if present (same file Python reads)
if [[ -f .env ]]; then
    set -a && source .env && set +a
fi

MODEL="${VLLM_MODEL:-${GEMMA_MODEL_ID:-google/gemma-4-e2b-it}}"
PORT="${VLLM_PORT:-8000}"
DTYPE="${VLLM_DTYPE:-bfloat16}"
MAX_LEN="${VLLM_MAX_LEN:-8192}"

if [[ -z "${VLLM_API_KEY:-}" ]]; then
    echo "ERROR: VLLM_API_KEY is not set."
    echo "  export VLLM_API_KEY=your-secret-token"
    echo "  or copy .env.example to .env and fill it in."
    exit 1
fi

echo "==> Starting vLLM server (via uv)"
echo "    model   : $MODEL"
echo "    port    : $PORT"
echo "    dtype   : $DTYPE"
echo "    max_len : $MAX_LEN"
echo ""

uv run vllm serve "$MODEL" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --api-key "$VLLM_API_KEY" \
    --dtype "$DTYPE" \
    --max-model-len "$MAX_LEN"
