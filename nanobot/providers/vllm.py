"""
vLLM provider — OpenAI-compatible client for the remote vLLM server.

Used exclusively by the sanitizer module for local PII detection.
Not wired into nanobot's main provider registry.

Required environment variables (set in .env or shell):
  VLLM_BASE_URL   Full URL to the vLLM server, e.g. http://192.168.1.100:8000/v1
  VLLM_API_KEY    Bearer token configured via --api-key on the vLLM server

Optional:
  VLLM_MODEL      Model name / LoRA alias as registered in vLLM
                  (default: google/gemma-4-e2b-it)

Start vLLM with auth enabled:
  vllm serve google/gemma-4-e2b-it --api-key <your-token> --port 8000

For LoRA / dynamic adapter switching, register adapters at startup:
  --enable-lora --lora-modules pii-lora=./adapters/pii
Then set VLLM_MODEL=pii-lora.
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

_MISSING = object()


def _require_env(name: str) -> str:
    value = os.environ.get(name, _MISSING)  # type: ignore[arg-type]
    if value is _MISSING or not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}\n"
            f"Add it to your .env file or export it before starting nanobot.\n"
            f"See nanobot/providers/vllm.py for documentation."
        )
    return value  # type: ignore[return-value]


def get_vllm_client() -> AsyncOpenAI:
    """
    Return a fresh AsyncOpenAI client pointed at the remote vLLM server.

    Reads VLLM_BASE_URL and VLLM_API_KEY at call time so that .env changes
    take effect without restarting Python (useful in tests).
    """
    base_url = _require_env("VLLM_BASE_URL")
    api_key = _require_env("VLLM_API_KEY")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def get_vllm_model() -> str:
    """Return the model name to use for vLLM calls."""
    return os.environ.get("VLLM_MODEL", "google/gemma-4-e2b-it")
