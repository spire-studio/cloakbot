from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.hooks.context import Intent, TurnContext
from cloakbot.privacy.hooks.post_llm import post_llm_hook
from cloakbot.privacy.hooks.pre_llm import pre_llm_hook


@pytest.mark.asyncio
async def test_pre_llm_hook_delegates_to_gateway() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="Revenue is 100 and cost is 60.",
        sanitized_input="Revenue is <<AMOUNT_1>> and cost is <<AMOUNT_2>>.",
        intent=Intent.MATH,
    )

    with patch(
        "cloakbot.privacy.hooks.pre_llm._GATEWAY.prepare",
        new=AsyncMock(
            return_value=(
                "Revenue is <<AMOUNT_1>> and cost is <<AMOUNT_2>>.\n\nPRIVACY_MATH_MODE",
                ctx,
                object(),
            )
        ),
    ) as mocked_prepare:
        user_message, result_ctx = await pre_llm_hook(
            "Revenue is 100 and cost is 60.",
            "cli:test",
        )

    mocked_prepare.assert_awaited_once_with(
        "Revenue is 100 and cost is 60.",
        "cli:test",
        fail_open=True,
    )
    assert result_ctx is ctx
    assert "PRIVACY_MATH_MODE" in user_message


@pytest.mark.asyncio
async def test_post_llm_hook_delegates_to_gateway() -> None:
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="Hi, my name is Laurie Luo",
        sanitized_input="Hi, my name is <<PERSON_1>>",
        intent=Intent.CHAT,
        was_sanitized=True,
    )

    with patch(
        "cloakbot.privacy.hooks.post_llm._GATEWAY.finalize",
        new=AsyncMock(return_value="Hello Laurie Luo"),
    ) as mocked_finalize:
        result = await post_llm_hook("Hello <<PERSON_1>>", ctx, "cli:test")

    mocked_finalize.assert_awaited_once_with(
        "Hello <<PERSON_1>>",
        ctx,
        include_report=True,
    )
    assert result == "Hello Laurie Luo"
