from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.agents.math_agent import MathAgent
from cloakbot.privacy.core.math_executer import LocalComputationRecord
from cloakbot.privacy.hooks.context import Intent, TurnContext



def _turn_context() -> TurnContext:
    return TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="Revenue is <<FINANCE_1>> and tax rate is <<PERCENTAGE_1>>.",
        sanitized_input="Revenue is <<FINANCE_1>> and tax rate is <<PERCENTAGE_1>>.",
        intent=Intent.MATH,
    )


@pytest.mark.asyncio
async def test_prepare_input_appends_math_execution_instruction() -> None:
    agent = MathAgent()
    ctx = _turn_context()

    prepared = await agent.prepare_input(ctx)

    assert prepared.startswith(ctx.sanitized_input)
    assert "PRIVACY MODE ENABLED" in prepared
    assert "FINANCE_1" in prepared
    assert "PERCENTAGE_1" in prepared


@pytest.mark.asyncio
async def test_finalize_output_delegates_to_math_executer() -> None:
    agent = MathAgent()
    ctx = _turn_context()

    with patch(
        "cloakbot.privacy.agents.math_agent.apply_privacy_math_with_details",
        new=AsyncMock(
            return_value=(
                "finalized",
                [
                    LocalComputationRecord(
                        snippet_index=1,
                        expression="FINANCE_1 * PERCENTAGE_1",
                        resolved_expression="100000 * 0.1",
                        result=10000,
                        formatted_result="10000",
                    )
                ],
            )
        ),
    ) as mocked:
        result = await agent.finalize_output("response", ctx)

    mocked.assert_awaited_once_with("response", "cli:test")
    assert result == "finalized"
    assert ctx.local_computations[0].formatted_result == "10000"
