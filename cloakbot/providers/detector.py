"""
Local Gemma 4 detector client — OpenAI-compatible.

Works against any OpenAI-compatible local backend (vLLM on a GPU box,
Ollama on a laptop, llama.cpp's HTTP server, etc.). Used exclusively by
the sanitizer for local PII detection; not wired into cloakbot's main
provider registry.

Connection settings come from the saved config's ``privacy`` section — the
single source of truth, written by ``cloakbot onboard`` -> [D] Privacy
Detector or the WebUI Settings -> Privacy tab:

  privacy.base_url   e.g. http://127.0.0.1:11434/v1   (Ollama)
                     or  http://192.168.1.100:8000/v1 (vLLM)
  privacy.api_key    Bearer token. For vLLM it must match --api-key on the
                     server. For Ollama any non-empty value works (no auth).
  privacy.model      Model tag / LoRA alias (default: google/gemma-4-E2B-it)

Keep the endpoint LOCAL: pointing it at a remote host sends raw input there
for detection and defeats the privacy boundary (TEST-ONLY).
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache

from openai import AsyncOpenAI

_DEFAULT_DETECTOR_MODEL = "google/gemma-4-E2B-it"


@dataclass(frozen=True)
class DetectorSettings:
    """Resolved local-detector connection settings."""

    base_url: str
    api_key: str
    model: str


@lru_cache
def _settings() -> DetectorSettings:
    """Resolve the local detector endpoint from the saved config's ``privacy``
    section (``cloakbot onboard`` -> [D] Privacy Detector, or the WebUI
    Settings -> Privacy tab). Raises a clear error if it is not configured.
    """
    base_url = api_key = model = None
    with suppress(Exception):
        from cloakbot.config.loader import load_config

        detector = load_config().privacy
        base_url, api_key, model = detector.base_url, detector.api_key, detector.model

    if not (base_url and api_key):
        raise RuntimeError(
            "Privacy detector is not configured. Run `cloakbot onboard` -> "
            "[D] Privacy Detector, or set it in the WebUI Settings -> Privacy tab."
        )

    return DetectorSettings(
        base_url=base_url,
        api_key=api_key,
        model=model or _DEFAULT_DETECTOR_MODEL,
    )


def get_detector_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client pointed at the local detector backend."""
    s = _settings()
    return AsyncOpenAI(base_url=s.base_url, api_key=s.api_key)


def get_detector_model() -> str:
    """Return the model name to use for local detection."""
    return _settings().model
