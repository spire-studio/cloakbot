"""
vLLM provider — OpenAI-compatible client for the remote vLLM server.

Used exclusively by the sanitizer module for local PII detection.
Not wired into nanobot's main provider registry.

Configuration is loaded from (in priority order):
  1. Environment variables
  2. .env file in the project root

Required variables:
  VLLM_BASE_URL   e.g. http://192.168.1.100:8000/v1
  VLLM_API_KEY    Bearer token (must match --api-key on the vLLM server)

Optional:
  VLLM_MODEL      Model name / LoRA alias (default: google/gemma-4-e2b-it)
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

    base_url: str = Field(alias="VLLM_BASE_URL")
    api_key: str = Field(alias="VLLM_API_KEY")
    model: str = Field(default="google/gemma-4-e2b-it", alias="VLLM_MODEL")


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
