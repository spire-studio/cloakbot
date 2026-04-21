from __future__ import annotations

from loguru import logger

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.agents.chat_agent import ChatAgent
from cloakbot.privacy.agents.math_agent import MathAgent
from cloakbot.privacy.hooks.context import Intent, TurnContext

_CHAT_AGENT = ChatAgent()
_MATH_AGENT = MathAgent()


def route_turn(ctx: TurnContext) -> Intent:
    """Choose the privacy task intent for a turn."""
    if ctx.intent is Intent.DOC:
        return Intent.DOC
    if ctx.intent is Intent.MATH:
        return Intent.MATH
    return Intent.CHAT


def get_agent(ctx: TurnContext) -> BaseAgent:
    """Return the concrete privacy agent for the routed turn."""
    if ctx.intent is Intent.MATH:
        return _MATH_AGENT
    if ctx.intent is Intent.DOC:
        logger.warning("DocAgent not yet implemented, falling back to ChatAgent")
        return _CHAT_AGENT
    return _CHAT_AGENT
