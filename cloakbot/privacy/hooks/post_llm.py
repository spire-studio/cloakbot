from __future__ import annotations

from cloakbot.privacy.agents.orchestrator import get_orchestrator
from cloakbot.privacy.hooks.context import TurnContext


async def post_llm_hook(
    response: str,
    ctx: TurnContext,
    session_key: str,
) -> str:
    """
    Called in loop.py after the LLM response arrives.
    Runs pass 2 detection, restores tokens, emits transparency report.
    """
    _ = session_key
    orchestrator = get_orchestrator()
    return await orchestrator.finalize_turn(response, ctx)
