from __future__ import annotations

from loguru import logger

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.agents.runtime.registry import get_registered_agent
from cloakbot.privacy.hooks.context import Intent, TurnContext


def route_turn(ctx: TurnContext) -> Intent:
    """Choose the privacy task intent for a turn."""
    if ctx.intent is Intent.DOC:
        return Intent.DOC
    if ctx.intent is Intent.MATH:
        return Intent.MATH
    return Intent.CHAT


def get_agent(ctx: TurnContext) -> BaseAgent:
    """Return the concrete privacy agent for the routed turn."""
    if ctx.intent is Intent.DOC:
        logger.warning("DocAgent not yet implemented, falling back to ChatAgent")
    return get_registered_agent(ctx.intent)
