from __future__ import annotations

from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.hub import ProtocolGateway

_GATEWAY = ProtocolGateway(channel="cli")


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
    prepared, ctx, _contract = await _GATEWAY.prepare(
        text,
        session_key,
        fail_open=fail_open,
    )
    return prepared, ctx
