from __future__ import annotations

from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.hub import ProtocolGateway

_GATEWAY = ProtocolGateway(channel="cli")


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
    return await _GATEWAY.finalize(response, ctx, include_report=include_report)
