#!/usr/bin/env bash
# Download Gemma 4 E2B weights for local vLLM serving.
# Run once before starting the server.
#
# Prerequisites:
#   pip install "huggingface_hub[cli]"
#   huggingface-cli login
#     (Gemma models are gated — accept the license at hf.co/google/gemma-4-e2b-it first)
#
# Override the model ID via env var if Google changes the HF path:
#   GEMMA_MODEL_ID=google/gemma-4-e2b-it bash scripts/download_model.sh

set -euo pipefail

MODEL_ID="${GEMMA_MODEL_ID:-google/gemma-4-e2b-it}"
LOCAL_DIR="${GEMMA_LOCAL_DIR:-./models/gemma-4-e2b}"

echo "==> Downloading $MODEL_ID to $LOCAL_DIR ..."
huggingface-cli download "$MODEL_ID" \
    --repo-type model \
    --local-dir "$LOCAL_DIR"

echo ""
echo "==> Done. Start the vLLM server with:"
echo "      bash scripts/start_vllm.sh"
echo ""
echo "    Or serve directly from HuggingFace (no local download needed):"
echo "      vllm serve $MODEL_ID --port 8000 --dtype bfloat16"
