"""
Local Gemma 4 detector client — OpenAI-compatible.

Works against any OpenAI-compatible local backend (vLLM on a GPU box,
Ollama on a laptop, llama.cpp's HTTP server, etc.). Used exclusively by
the sanitizer for local PII detection; not wired into cloakbot's main
provider registry.

Configuration is loaded from (in priority order):
  1. Environment variables
  2. .env file in the project root

Required variables:
  GEMMA_BASE_URL   e.g. http://127.0.0.1:11434/v1   (Ollama)
                   or  http://192.168.1.100:8000/v1 (vLLM)
  GEMMA_API_KEY    Bearer token. For vLLM it must match --api-key on the
                   server. For Ollama any non-empty value works (no auth).

Optional:
  GEMMA_MODEL      Model tag / LoRA alias (default: google/gemma-4-E2B-it)
"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VllmSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    base_url: str = Field(alias="GEMMA_BASE_URL")
    api_key: str = Field(alias="GEMMA_API_KEY")
    model: str = Field(default="google/gemma-4-E2B-it", alias="GEMMA_MODEL")


@lru_cache
def _settings() -> VllmSettings:
    return VllmSettings()  # type: ignore[call-arg]


def get_vllm_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client pointed at the remote vLLM server."""
    s = _settings()
    return AsyncOpenAI(base_url=s.base_url, api_key=s.api_key)


def get_vllm_model() -> str:
    """Return the model name to use for vLLM calls."""
    return _settings().model
