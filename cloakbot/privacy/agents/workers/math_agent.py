from __future__ import annotations

from cloakbot.privacy.agents.base import BaseAgent
from cloakbot.privacy.core.math.math_executor import (
    apply_privacy_math_for_turn,
    build_math_execution_instruction,
)
from cloakbot.privacy.hooks.context import TurnContext


class MathAgent(BaseAgent):
    """Privacy agent for math turns that require local computation."""

    async def prepare_input(self, ctx: TurnContext) -> str:
        instruction = build_math_execution_instruction(ctx.sanitized_input, ctx.session_key)
        return f"{ctx.sanitized_input}\n\n{instruction}"

    async def finalize_output(self, response: str, ctx: TurnContext) -> str:
        result = await apply_privacy_math_for_turn(response, ctx.session_key, turn_id=ctx.turn_id)
        ctx.local_computations = result.computations
        ctx.remote_history_output = result.remote_history_text
        return result.display_text
