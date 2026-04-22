from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.agents.runtime.orchestrator import PrivacyOrchestrator
from cloakbot.privacy.hooks.context import Intent
from cloakbot.privacy.protocol.contracts import EventType
from cloakbot.privacy.protocol.observability import get_event_sink


@pytest.mark.asyncio
async def test_prepare_turn_emits_received_and_sanitize_events() -> None:
    orchestrator = PrivacyOrchestrator()
    sink = get_event_sink()
    sink.clear()

    with patch(
        "cloakbot.privacy.agents.runtime.orchestrator.sanitize_input_with_detection",
        new=AsyncMock(return_value=("hello", False, [], None)),
    ), patch(
        "cloakbot.privacy.agents.runtime.orchestrator.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ), patch(
        "cloakbot.privacy.agents.runtime.orchestrator.get_agent",
        return_value=AsyncMock(prepare_input=AsyncMock(return_value="hello")),
    ):
        await orchestrator.prepare_turn("hello", "session:test")

    event_types = [event.event_type for event in sink.events]
    assert EventType.TURN_RECEIVED in event_types
    assert EventType.TURN_SANITIZE_STARTED in event_types
    assert EventType.TURN_SANITIZE_SUCCEEDED in event_types
    assert EventType.TURN_DISPATCH_STARTED in event_types


@pytest.mark.asyncio
async def test_finalize_turn_emits_restore_and_completed_events() -> None:
    orchestrator = PrivacyOrchestrator()
    sink = get_event_sink()
    sink.clear()

    agent = AsyncMock()
    agent.finalize_output = AsyncMock(return_value="sanitized")

    with patch(
        "cloakbot.privacy.agents.runtime.orchestrator.get_agent",
        return_value=agent,
    ), patch(
        "cloakbot.privacy.agents.runtime.orchestrator.remap_response_with_annotations",
        new=AsyncMock(return_value=("restored", [])),
    ):
        prepared, ctx = await orchestrator.prepare_turn("hello", "session:test", fail_open=True)
        assert prepared
        result = await orchestrator.finalize_turn("model-response", ctx, include_report=False)

    assert result == "restored"
    event_types = [event.event_type for event in sink.events]
    assert EventType.TURN_RESTORE_STARTED in event_types
    assert EventType.TURN_RESTORE_COMPLETED in event_types
    assert EventType.TURN_COMPLETED in event_types
