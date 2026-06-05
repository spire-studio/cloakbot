"""
Local Gemma 4 detector client — OpenAI-compatible.

Works against any OpenAI-compatible local backend (vLLM on a GPU box,
Ollama on a laptop, llama.cpp's HTTP server, etc.). Used exclusively by
the sanitizer for local PII detection; not wired into cloakbot's main
provider registry.

Configuration is loaded from (in priority order):
  1. Environment variables (GEMMA_*)
  2. .env file in the project root
  3. The saved config's ``privacy`` section (written by ``cloakbot onboard``)

Required variables:
  GEMMA_BASE_URL   e.g. http://127.0.0.1:11434/v1   (Ollama)
                   or  http://192.168.1.100:8000/v1 (vLLM)
  GEMMA_API_KEY    Bearer token. For vLLM it must match --api-key on the
                   server. For Ollama any non-empty value works (no auth).

Optional:
  GEMMA_MODEL      Model tag / LoRA alias (default: google/gemma-4-E2B-it)
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache

from openai import AsyncOpenAI
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DETECTOR_MODEL = "google/gemma-4-E2B-it"


class VllmSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Optional so the resolver can fall back to the saved config's ``privacy``
    # section (written by ``cloakbot onboard``) when GEMMA_* / .env are absent.
    base_url: str | None = Field(default=None, alias="GEMMA_BASE_URL")
    api_key: str | None = Field(default=None, alias="GEMMA_API_KEY")
    model: str | None = Field(default=None, alias="GEMMA_MODEL")


@dataclass(frozen=True)
class DetectorSettings:
    """Resolved local-detector connection settings."""

    base_url: str
    api_key: str
    model: str


@lru_cache
def _settings() -> DetectorSettings:
    """Resolve the local detector endpoint.

    Priority: ``GEMMA_*`` env vars / ``.env`` (explicit override, back-compat)
    → the saved config's ``privacy`` section (written by ``cloakbot onboard``).
    Raises a clear error if neither is configured.
    """
    env = VllmSettings()
    base_url, api_key, model = env.base_url, env.api_key, env.model

    if not (base_url and api_key):
        with suppress(Exception):
            from cloakbot.config.loader import get_config_path, load_config

            if get_config_path().exists():
                detector = load_config().privacy
                base_url = base_url or detector.base_url
                api_key = api_key or detector.api_key
                model = model or detector.model

    if not (base_url and api_key):
        raise RuntimeError(
            "Privacy detector is not configured. Run `cloakbot onboard` -> "
            "[D] Privacy Detector, or set GEMMA_BASE_URL / GEMMA_API_KEY in .env."
        )

    return DetectorSettings(
        base_url=base_url,
        api_key=api_key,
        model=model or _DEFAULT_DETECTOR_MODEL,
    )


def get_vllm_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client pointed at the local detector backend."""
    s = _settings()
    return AsyncOpenAI(base_url=s.base_url, api_key=s.api_key)


def get_vllm_model() -> str:
    """Return the model name to use for local detection."""
    return _settings().model
