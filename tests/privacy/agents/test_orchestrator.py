from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from cloakbot.privacy.agents.orchestrator import PrivacyOrchestrator
from cloakbot.privacy.core.math_executer import LocalComputationRecord
from cloakbot.privacy.core.restorer import RestoredTokenAnnotation
from cloakbot.privacy.core.types import GeneralEntity, DetectionResult
from cloakbot.privacy.hooks.context import Intent, TurnContext


def _entity(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


@pytest.mark.asyncio
async def test_prepare_turn_populates_turn_context_for_chat() -> None:
    orchestrator = PrivacyOrchestrator()
    detection = DetectionResult(
        original_prompt="Hello Laurie Luo",
        entities=[_entity("Laurie Luo", "person")],
        llm_raw_output="",
        latency_ms=1.0,
    )

    with patch(
        "cloakbot.privacy.agents.orchestrator.sanitize_input_with_detection",
        new=AsyncMock(
            return_value=("Hello <<PERSON_1>>", True, detection.sensitive_entities, detection)
        ),
    ), patch(
        "cloakbot.privacy.agents.orchestrator.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ):
        prepared, ctx = await orchestrator.prepare_turn(
            "Hello Laurie Luo",
            "cli:test",
        )

    assert prepared == "Hello <<PERSON_1>>"
    assert ctx.session_key == "cli:test"
    assert ctx.raw_input == "Hello Laurie Luo"
    assert ctx.sanitized_input == "Hello <<PERSON_1>>"
    assert ctx.was_sanitized is True
    assert ctx.user_input_entities == detection.sensitive_entities
    assert ctx.intent is Intent.CHAT


@pytest.mark.asyncio
async def test_prepare_turn_routes_math_from_intent() -> None:
    orchestrator = PrivacyOrchestrator()
    detection = DetectionResult(
        original_prompt="What is 12% of 100?",
        entities=[],
        llm_raw_output="",
        latency_ms=1.0,
    )

    with patch(
        "cloakbot.privacy.agents.orchestrator.sanitize_input_with_detection",
        new=AsyncMock(return_value=("What is <<AMOUNT_1>> of <<AMOUNT_2>>?", True, [], detection)),
    ), patch(
        "cloakbot.privacy.agents.orchestrator.analyze_user_intent",
        new=AsyncMock(return_value=Intent.MATH),
    ):
        prepared, ctx = await orchestrator.prepare_turn(
            "What is 12% of 100?",
            "cli:test",
        )

    assert prepared.startswith("What is <<AMOUNT_1>> of <<AMOUNT_2>>?")
    assert "PRIVACY MODE ENABLED" in prepared
    assert ctx.intent is Intent.MATH


@pytest.mark.asyncio
async def test_finalize_turn_restores_tokens_and_emits_report() -> None:
    orchestrator = PrivacyOrchestrator()
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
        "cloakbot.privacy.agents.orchestrator.remap_response_with_annotations",
        new=AsyncMock(return_value=("Hello Laurie Luo", [])),
    ), patch(
        "cloakbot.privacy.agents.orchestrator.get_agent",
        return_value=agent,
    ):
        result = await orchestrator.finalize_turn(
            "Hello <<PERSON_1>>",
            ctx,
        )

    agent.finalize_output.assert_awaited_once_with("Hello <<PERSON_1>>", ctx)
    assert result.startswith("Hello Laurie Luo")
    assert ctx.display_output == "Hello Laurie Luo"
    assert ctx.display_output_annotations == []
    assert "Privacy Report" in result


@pytest.mark.asyncio
async def test_finalize_turn_can_skip_report_for_webui() -> None:
    orchestrator = PrivacyOrchestrator()
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
        "cloakbot.privacy.agents.orchestrator.remap_response_with_annotations",
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
    ), patch(
        "cloakbot.privacy.agents.orchestrator.get_agent",
        return_value=agent,
    ):
        result = await orchestrator.finalize_turn(
            "Hello <<PERSON_1>>",
            ctx,
            include_report=False,
        )

    assert result == "Hello Laurie Luo"
    assert len(ctx.display_output_annotations) == 1
    assert ctx.display_output_annotations[0].placeholder == "<<PERSON_1>>"


@pytest.mark.asyncio
async def test_finalize_turn_adds_local_computation_annotations() -> None:
    orchestrator = PrivacyOrchestrator()
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
        "cloakbot.privacy.agents.orchestrator.remap_response_with_annotations",
        new=AsyncMock(return_value=("The result is 252150000.", [])),
    ), patch(
        "cloakbot.privacy.agents.orchestrator.get_agent",
        return_value=agent,
    ):
        result = await orchestrator.finalize_turn(
            "The result is 252150000.",
            ctx,
            include_report=False,
        )

    assert result == "The result is 252150000."
    assert len(ctx.display_output_annotations) == 1
    assert ctx.display_output_annotations[0].annotation_type == "local_computation"
    assert ctx.display_output_annotations[0].formula == "205000000 * 1.23"
