from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.hooks.context import Intent, TurnContext
from cloakbot.privacy.protocol.hub import ProtocolGateway


@pytest.mark.asyncio
async def test_protocol_gateway_prepare_builds_turn_contract() -> None:
    gateway = ProtocolGateway(channel="cli")

    with patch(
        "cloakbot.privacy.protocol.hub.sanitize_input_with_detection",
        new=AsyncMock(return_value=("sanitized", True, [], None)),
    ), patch(
        "cloakbot.privacy.protocol.hub.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ), patch(
        "cloakbot.privacy.protocol.hub.get_registered_agent",
        return_value=AsyncMock(prepare_input=AsyncMock(return_value="prepared")),
    ):
        prepared, ctx, contract = await gateway.prepare("hello", "session:test")

    assert prepared == "prepared"
    assert isinstance(ctx, TurnContext)
    assert contract.context.intent == "chat"
    assert contract.payload["sanitized_input"] == "sanitized"


@pytest.mark.asyncio
async def test_protocol_gateway_finalize_completes_turn_contract() -> None:
    gateway = ProtocolGateway(channel="cli")
    ctx = TurnContext(session_key="session:test", turn_id="turn-1", raw_input="hello", intent=Intent.CHAT)

    with patch(
        "cloakbot.privacy.protocol.hub.get_registered_agent",
        return_value=AsyncMock(finalize_output=AsyncMock(return_value="sanitized-output")),
    ), patch(
        "cloakbot.privacy.protocol.hub.remap_response_with_annotations",
        new=AsyncMock(return_value=("restored", [])),
    ):
        restored = await gateway.finalize("model-output", ctx, include_report=False)

    assert restored == "restored"
