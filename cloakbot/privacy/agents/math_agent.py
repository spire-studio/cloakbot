from __future__ import annotations

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.core.math_executer import (
    apply_privacy_math_with_details,
    build_math_execution_instruction,
)
from cloakbot.privacy.hooks.context import TurnContext


class MathAgent(BaseAgent):
    """Privacy agent for math turns that require local computation."""

    async def prepare_input(self, ctx: TurnContext) -> str:
        instruction = build_math_execution_instruction(ctx.sanitized_input)
        return f"{ctx.sanitized_input}\n\n{instruction}"

    async def finalize_output(self, response: str, ctx: TurnContext) -> str:
        finalized, computations = await apply_privacy_math_with_details(response, ctx.session_key)
        ctx.local_computations = computations
        return finalized
