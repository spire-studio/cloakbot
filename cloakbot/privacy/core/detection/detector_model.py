"""Shared PydanticAI model binding for the local privacy detector.

Every detector/classifier agent (general, digit, intent) talks to the SAME
local OpenAI-compatible endpoint — Gemma served by vLLM/Ollama, configured in
``config.privacy``. This module builds that one PydanticAI model so the
connection decision lives in a single place instead of being re-derived per
detector.

Trust boundary: the endpoint is LOCAL. Wrapping the call in PydanticAI changes
nothing about what leaves the machine — the local detector sees raw input by
design (that is its whole job). The single source of truth for the endpoint is
``cloakbot/providers/detector.py``; this module reuses its client so the
"keep the endpoint LOCAL" invariant is unchanged. See ``docs/domains/privacy.md``.

Output mode: detectors use ``NativeOutput`` — the local endpoint advertises
JSON-Schema structured output, so PydanticAI constrains decoding to the entity
schema. The hand-tuned detector prompts stay byte-for-byte (the schema travels
in the API ``response_format`` field, not in the prompt).

Two requirements learned from live testing on a local Ollama:
- Use a capable detector model. A heavily quantized 4-bit build (e.g. a 4-bit
  MLX Gemma e2b) silently returns ``{"entities": []}`` for the complex general
  extraction regardless of output mode; an 8-bit build (e.g. e2b-mxfp8) is
  reliable. Set it via ``config.privacy.model``.
- Detection runs SEQUENTIALLY (see ``PiiDetector``), not concurrently: firing
  both detectors at a single-instance local backend thrashes it.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_ai.messages import TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from cloakbot.providers.detector import get_detector_client, get_detector_model


@lru_cache(maxsize=1)
def build_detector_model() -> Model:
    """Build the shared PydanticAI model for the local detector endpoint.

    Reuses the existing ``config.privacy``-resolved ``AsyncOpenAI`` client, so
    endpoint/auth/timeout policy stays in ``providers/detector.py``. Cached for
    the process: the underlying client is constructed once and shared by every
    detector agent.
    """
    return OpenAIChatModel(
        get_detector_model(),
        provider=OpenAIProvider(openai_client=get_detector_client()),
    )


def response_text(result: object) -> str:
    """Return the final model text from a completed agent run (for logging).

    Detectors record the raw detector output in ``DetectionResult`` purely for
    the event log; this recovers the last text part. Returns ``""`` when no
    text part is present.
    """
    for message in reversed(result.all_messages()):  # type: ignore[attr-defined]
        for part in getattr(message, "parts", ()):
            if isinstance(part, TextPart):
                return part.content
    return ""


__all__ = ["build_detector_model", "response_text"]
