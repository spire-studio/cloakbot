import base64
from unittest.mock import AsyncMock, Mock, patch

import pytest

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.core.types import DetectionResult, GeneralEntity
from cloakbot.privacy.hooks.context import Intent, TurnContext
from cloakbot.privacy.protocol.contracts import EventType
from cloakbot.privacy.protocol.observability import get_event_sink
from cloakbot.privacy.runtime.pipeline import PrivacyRuntime
from cloakbot.privacy.visual_redaction import (
    VisualBlocksResult,
    VisualPrivacyRedaction,
    VisualVaultEntry,
)

# Smallest possible PNG payload — pre-encoded by hand so the magic bytes match
# detect_image_mime() and the file passes the "is it an image?" gate.
_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAfbLI3wAAAABJRU5ErkJggg=="
)


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


@pytest.mark.asyncio
async def test_runtime_prepare_turn_routes_user_attached_images_through_visual_pipeline(
    tmp_path,
) -> None:
    """User-attached prompt images must go through ``process_visual_blocks``.

    Regression coverage for the historical leak where ``pre_llm_hook`` only
    received text, letting the raw image bytes flow straight to the remote
    LLM via the context builder's untouched media path.
    """
    runtime = PrivacyRuntime(channel="cli")

    image_path = tmp_path / "invoice.png"
    image_path.write_bytes(_TINY_PNG_BYTES)
    redacted_blocks = [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,cmVkYWN0ZWQ="},
            "_meta": {"path": str(image_path)},
        }
    ]
    visual_record = VisualPrivacyRedaction(
        sourcePath=str(image_path),
        status="redacted",
        detectedItems=1,
        redactionBoxes=1,
        labels=["customer_name"],
    )
    visual_result = VisualBlocksResult(
        redacted_blocks=redacted_blocks,
        sanitized_text="Hello <<PERSON_1>>",
        modified=True,
        entities=[_entity("Laurie", "person")],
        visual_redactions=[visual_record],
        vault_entries=[
            VisualVaultEntry(
                kind="redacted_image",
                path=str(tmp_path / "redacted.png"),
                media_type="image/png",
            ),
            VisualVaultEntry(
                kind="ocr_sanitized_text",
                path=str(tmp_path / "ocr.txt"),
                media_type="text/plain",
            ),
        ],
        omitted_count=0,
        image_count=1,
    )

    captured_blocks: list[list[dict]] = []

    async def fake_process(blocks, **_kwargs):
        captured_blocks.append(blocks)
        return visual_result

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(return_value=("look at this", False, [], None)),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.process_visual_blocks",
        new=AsyncMock(side_effect=fake_process),
    ):
        prepared, ctx = await runtime.prepare_turn(
            "look at this",
            "cli:test",
            media=[str(image_path)],
        )

    # The processed-blocks list is what reaches the remote LLM, so check it
    # tightly: the redacted image block must be present, and the user-typed
    # text must follow as a separate text block.
    assert isinstance(prepared, list)
    assert prepared[0] == redacted_blocks[0]
    assert prepared[-1] == {"type": "text", "text": "look at this"}

    # And process_visual_blocks must have been handed a fresh image_url
    # block — not the raw filesystem path — so the visual detector sees the
    # bytes, not a path string.
    assert len(captured_blocks) == 1
    only_call = captured_blocks[0]
    assert only_call[0]["type"] == "image_url"
    assert only_call[0]["image_url"]["url"].startswith("data:image/png;base64,")

    assert ctx.user_input_visual_redactions == [visual_record]
    assert [a.kind for a in ctx.user_input_vault_artifacts] == [
        "redacted_image",
        "ocr_sanitized_text",
    ]
    assert ctx.user_input_entities == [_entity("Laurie", "person")]
    assert ctx.was_sanitized is True


@pytest.mark.asyncio
async def test_runtime_prepare_turn_fails_closed_when_visual_pipeline_raises(
    tmp_path,
) -> None:
    """Visual pipeline failure must drop the attachment, never forward it."""
    runtime = PrivacyRuntime(channel="cli")
    image_path = tmp_path / "invoice.png"
    image_path.write_bytes(_TINY_PNG_BYTES)

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(return_value=("hi", False, [], None)),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.process_visual_blocks",
        new=AsyncMock(side_effect=RuntimeError("vllm down")),
    ):
        prepared, _ctx = await runtime.prepare_turn(
            "hi",
            "cli:test",
            media=[str(image_path)],
        )

    assert isinstance(prepared, list)
    # No image_url block survives the failure; the user only sees the
    # placeholder + the text turn.
    assert not any(block.get("type") == "image_url" for block in prepared)
    placeholder = next(block for block in prepared if block.get("type") == "text")
    assert "visual privacy pipeline unavailable" in placeholder["text"]
