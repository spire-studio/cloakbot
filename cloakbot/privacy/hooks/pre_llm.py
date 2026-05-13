from __future__ import annotations

from typing import Any

from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.runtime import get_runtime

_RUNTIME = get_runtime()


async def pre_llm_hook(
    text: str,
    session_key: str,
    *,
    media: list[str] | None = None,
    fail_open: bool = True,
) -> tuple[str | list[dict[str, Any]], TurnContext]:
    """Called in loop.py before the LLM call.

    Returns ``(prepared_content, TurnContext)``. ``prepared_content`` is a
    plain string for text-only turns, or a list of OpenAI-style content
    blocks when the user attached images — in which case the visual
    privacy pipeline (vLLM detection + local OCR redaction, with a
    fail-closed default) has already been applied. The :class:`TurnContext`
    must be threaded into :func:`post_llm_hook`.
    """
    prepared, ctx = await _RUNTIME.prepare_turn(
        text,
        session_key,
        media=media,
        fail_open=fail_open,
    )
    return prepared, ctx
