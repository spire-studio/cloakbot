from __future__ import annotations

from cloakbot.privacy.agents.orchestrator import get_orchestrator
from cloakbot.privacy.hooks.context import TurnContext


async def pre_llm_hook(
    text: str,
    session_key: str,
    *,
    fail_open: bool = True,
) -> tuple[str, TurnContext]:
    """
    Called in loop.py before the LLM call.
    Returns (sanitized_text, TurnContext).
    The TurnContext must be passed to post_llm_hook().
    """
    orchestrator = get_orchestrator()
    return await orchestrator.prepare_turn(
        text,
        session_key,
        fail_open=fail_open,
    )
