from unittest.mock import AsyncMock, Mock, patch

import pytest

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.core.types import DetectionResult, GeneralEntity
from cloakbot.privacy.hooks.context import Intent, TurnContext
from cloakbot.privacy.protocol.contracts import EventType
from cloakbot.privacy.protocol.observability import get_event_sink
from cloakbot.privacy.runtime.pipeline import PrivacyRuntime


def _entity(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


@pytest.mark.asyncio
async def test_runtime_prepare_turn_emits_prepare_chain_events_in_order() -> None:
    runtime = PrivacyRuntime(channel="cli")
    sink = get_event_sink()
    sink.clear()

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(return_value=("hello", False, [], None)),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.select_worker",
        return_value=AsyncMock(prepare_input=AsyncMock(return_value="hello")),
    ):
        prepared, ctx = await runtime.prepare_turn("hello", "session:test")

    assert prepared == "hello"
    event_types = [event.event_type for event in sink.events]
    expected_chain = [
        EventType.TURN_RECEIVED,
        EventType.TURN_SANITIZE_STARTED,
        EventType.TURN_SANITIZE_SUCCEEDED,
        EventType.TURN_INTENT_CLASSIFIED,
        EventType.TURN_DISPATCH_STARTED,
        EventType.TURN_DISPATCH_COMPLETED,
    ]
    indices = [event_types.index(event_type) for event_type in expected_chain]
    assert indices == sorted(indices)
    assert ctx.intent is Intent.CHAT


@pytest.mark.asyncio
async def test_runtime_prepare_turn_populates_turn_context_for_chat() -> None:
    runtime = PrivacyRuntime(channel="cli")
    detection = DetectionResult(
        original_prompt="Hello Laurie Luo",
        entities=[_entity("Laurie Luo", "person")],
        llm_raw_output="",
        latency_ms=1.0,
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(
            return_value=("Hello <<PERSON_1>>", True, detection.sensitive_entities, detection)
        ),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ):
        prepared, ctx = await runtime.prepare_turn("Hello Laurie Luo", "cli:test")

    assert prepared == "Hello <<PERSON_1>>"
    assert ctx.session_key == "cli:test"
    assert ctx.raw_input == "Hello Laurie Luo"
    assert ctx.sanitized_input == "Hello <<PERSON_1>>"
    assert ctx.was_sanitized is True
    assert ctx.user_input_entities == detection.sensitive_entities
    assert ctx.intent is Intent.CHAT


@pytest.mark.asyncio
async def test_runtime_prepare_turn_routes_math_intent_to_math_worker() -> None:
    runtime = PrivacyRuntime(channel="cli")
    detection = DetectionResult(
        original_prompt="What is 12% of 100?",
        entities=[],
        llm_raw_output="",
        latency_ms=1.0,
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(return_value=("What is <<AMOUNT_1>> of <<AMOUNT_2>>?", True, [], detection)),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.MATH),
    ):
        prepared, ctx = await runtime.prepare_turn("What is 12% of 100?", "cli:test")

    assert prepared.startswith("What is <<AMOUNT_1>> of <<AMOUNT_2>>?")
    assert "PRIVACY MODE ENABLED" in prepared
    assert ctx.intent is Intent.MATH


@pytest.mark.asyncio
async def test_runtime_finalize_turn_emits_restore_and_turn_completion_events() -> None:
    runtime = PrivacyRuntime(channel="cli")
    sink = get_event_sink()
    sink.clear()
    agent = AsyncMock()
    agent.prepare_input = AsyncMock(return_value="hello")
    agent.finalize_output = AsyncMock(return_value="sanitized")

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(return_value=("hello", False, [], None)),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.select_worker",
        return_value=agent,
    ), patch(
        "cloakbot.privacy.runtime.pipeline.remap_response_with_annotations",
        new=AsyncMock(return_value=("restored", [])),
    ):
        _, ctx = await runtime.prepare_turn("hello", "session:test")
        result = await runtime.finalize_turn("model-output", ctx, include_report=False)

    assert result == "restored"
    restore_completed = next(event for event in sink.events if event.event_type is EventType.TURN_RESTORE_COMPLETED)
    turn_completed = next(event for event in sink.events if event.event_type is EventType.TURN_COMPLETED)
    assert restore_completed.duration_ms is not None
    assert turn_completed.duration_ms is not None
    assert sink.events.index(restore_completed) < sink.events.index(turn_completed)


@pytest.mark.asyncio
async def test_runtime_finalize_turn_restores_tokens_and_emits_report() -> None:
    runtime = PrivacyRuntime(channel="cli")
    agent = Mock()
    agent.finalize_output = AsyncMock(return_value="Hello <<PERSON_1>>")
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="Hi, my name is Laurie Luo",
        sanitized_input="Hi, my name is <<PERSON_1>>",
        intent=Intent.CHAT,
        was_sanitized=True,
        user_input_entities=[_entity("Laurie Luo", "person")],
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.select_worker",
        return_value=agent,
    ), patch(
        "cloakbot.privacy.runtime.pipeline.remap_response_with_annotations",
        new=AsyncMock(return_value=("Hello Laurie Luo", [])),
    ):
        result = await runtime.finalize_turn("Hello <<PERSON_1>>", ctx)

    agent.finalize_output.assert_awaited_once_with("Hello <<PERSON_1>>", ctx)
    assert result.startswith("Hello Laurie Luo")
    assert ctx.display_output == "Hello Laurie Luo"
    assert ctx.display_output_annotations == []
    assert "Privacy Report" in result


@pytest.mark.asyncio
async def test_runtime_finalize_turn_can_skip_report() -> None:
    runtime = PrivacyRuntime(channel="cli")
    agent = Mock()
    agent.finalize_output = AsyncMock(return_value="Hello <<PERSON_1>>")
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="Hi, my name is Laurie Luo",
        sanitized_input="Hi, my name is <<PERSON_1>>",
        intent=Intent.CHAT,
        was_sanitized=True,
        user_input_entities=[_entity("Laurie Luo", "person")],
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.select_worker",
        return_value=agent,
    ), patch(
        "cloakbot.privacy.runtime.pipeline.remap_response_with_annotations",
        new=AsyncMock(
            return_value=(
                "Hello Laurie Luo",
                [
                    RestoredTokenAnnotation(
                        placeholder="<<PERSON_1>>",
                        text="Laurie Luo",
                        start=6,
                        end=16,
                        entity_type="person",
                        severity="high",
                        canonical="Laurie Luo",
                        aliases=["Laurie Luo"],
                        value=None,
                    )
                ],
            )
        ),
    ):
        result = await runtime.finalize_turn("Hello <<PERSON_1>>", ctx, include_report=False)

    assert result == "Hello Laurie Luo"
    assert len(ctx.display_output_annotations) == 1
    assert ctx.display_output_annotations[0].placeholder == "<<PERSON_1>>"


@pytest.mark.asyncio
async def test_runtime_finalize_turn_adds_local_computation_annotations() -> None:
    runtime = PrivacyRuntime(channel="cli")
    agent = Mock()
    agent.finalize_output = AsyncMock(return_value="The result is 252150000.")
    ctx = TurnContext(
        session_key="cli:test",
        turn_id="turn-1",
        raw_input="What is my acquisition after it increases by 23%?",
        sanitized_input="What is my acquisition after it increases by <<PERCENTAGE_1>>?",
        intent=Intent.MATH,
        local_computations=[
            LocalComputationRecord(
                snippet_index=1,
                expression="FINANCE_1 * 1.23",
                resolved_expression="205000000 * 1.23",
                result=252150000,
                formatted_result="252150000",
            )
        ],
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.select_worker",
        return_value=agent,
    ), patch(
        "cloakbot.privacy.runtime.pipeline.remap_response_with_annotations",
        new=AsyncMock(return_value=("The result is 252150000.", [])),
    ):
        result = await runtime.finalize_turn("The result is 252150000.", ctx, include_report=False)

    assert result == "The result is 252150000."
    assert len(ctx.display_output_annotations) == 1
    assert ctx.display_output_annotations[0].annotation_type == "local_computation"
    assert ctx.display_output_annotations[0].formula == "205000000 * 1.23"
