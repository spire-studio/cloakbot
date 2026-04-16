from __future__ import annotations

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.hooks.context import TurnContext


class ChatAgent(BaseAgent):
    """Default privacy agent for standard chat turns."""

    async def prepare_input(self, ctx: TurnContext) -> str:
        return ctx.sanitized_input

    async def finalize_output(self, response: str, ctx: TurnContext) -> str:
        return response
