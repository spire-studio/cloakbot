#!/usr/bin/env bash
# Start the local vLLM server for sanitizer PII detection.
#
# Env overrides:
#   GEMMA_MODEL_ID   HuggingFace model ID or local path (default: google/gemma-4-e2b-it)
#   VLLM_PORT        Port to listen on (default: 8000)
#   VLLM_DTYPE       Torch dtype (default: bfloat16; use float16 for older GPUs)
#   VLLM_MAX_LEN     Max context length in tokens (default: 8192)
#
# For LoRA / dynamic adapter switching, add:
#   --enable-lora --lora-modules <name>=<path>

set -euo pipefail

MODEL="${GEMMA_MODEL_ID:-google/gemma-4-e2b-it}"
PORT="${VLLM_PORT:-8000}"
DTYPE="${VLLM_DTYPE:-bfloat16}"
MAX_LEN="${VLLM_MAX_LEN:-8192}"

echo "==> Starting vLLM server"
echo "    model   : $MODEL"
echo "    port    : $PORT"
echo "    dtype   : $DTYPE"
echo "    max_len : $MAX_LEN"
echo ""

vllm serve "$MODEL" \
    --dtype "$DTYPE" \
    --port "$PORT" \
    --max-model-len "$MAX_LEN"
