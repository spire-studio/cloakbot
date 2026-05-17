from __future__ import annotations

import pytest

from cloakbot.privacy.agents.workers.chat_agent import ChatAgent
from cloakbot.privacy.hooks.context import Intent, TurnContext


def _turn_context(sanitized_input: str) -> TurnContext:
    return TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input=sanitized_input,
        sanitized_input=sanitized_input,
        intent=Intent.CHAT,
    )


@pytest.mark.asyncio
async def test_prepare_input_appends_local_path_tool_instruction() -> None:
    agent = ChatAgent()
    ctx = _turn_context("Please read <<LOCAL_PATH_1>> and summarize the invoice.")

    prepared = await agent.prepare_input(ctx)

    assert prepared.startswith(ctx.sanitized_input)
    assert "call read_file with that placeholder first" in prepared
    assert "Do not ask the user to upload" in prepared


@pytest.mark.asyncio
async def test_prepare_input_leaves_normal_chat_unchanged() -> None:
    agent = ChatAgent()
    ctx = _turn_context("Hello <<PERSON_1>>")

    prepared = await agent.prepare_input(ctx)

    assert prepared == ctx.sanitized_input
