from __future__ import annotations

from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.runtime import get_runtime

_RUNTIME = get_runtime()


async def post_llm_hook(
    response: str,
    ctx: TurnContext,
    session_key: str,
    *,
    include_report: bool = True,
) -> str:
    """
    Called in loop.py after the LLM response arrives.
    Runs pass 2 detection, restores tokens, emits transparency report.
    """
    _ = session_key
    return await _RUNTIME.finalize_turn(response, ctx, include_report=include_report)
