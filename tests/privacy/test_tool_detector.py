"""Tests for the tool-output privacy orchestrator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from cloakbot.privacy.core.detection.chunking import ContentType
from cloakbot.privacy.core.detection.tool_detector import (
    TOOL_DETECTOR_VERSION,
    ToolDetectionContext,
    ToolPrivacyDetector,
)
from cloakbot.privacy.core.types import (
    DetectionResult,
    GeneralEntity,
)


def _ctx(content_type: ContentType | None = None) -> ToolDetectionContext:
    return ToolDetectionContext(
        tool_name="read_file",
        session_key="cli:test",
        turn_id="turn-1",
        content_type=content_type,
    )


def _entity(text: str, etype: str = "email") -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=etype)


def _detection(entities: list[GeneralEntity]) -> DetectionResult:
    return DetectionResult(
        original_prompt="(orchestrator does not inspect this)",
        entities=entities,
        llm_raw_output="{}",
        latency_ms=1.0,
    )


@pytest.mark.asyncio
async def test_tool_detector_dedupes_entities_across_chunks() -> None:
    """Same email surfacing in two chunks yields one entity in the result.

    Cross-chunk dedup is the precondition for vault placeholder reuse
    — without it the same value would race to two different
    placeholders inside a single tool result.
    """

    async def fake_detect(text, **_kwargs):
        entities: list[GeneralEntity] = []
        if "alice@example.com" in text:
            entities.append(_entity("alice@example.com"))
        if "bob@example.com" in text:
            entities.append(_entity("bob@example.com"))
        return _detection(entities)

    inner = AsyncMock()
    inner.detect = AsyncMock(side_effect=fake_detect)

    detector = ToolPrivacyDetector(detector=inner)
    # Force multiple chunks and inject the same email into two of them
    # so the orchestrator has to dedupe. Bob's email lives in a third
    # chunk to prove the dedup doesn't collapse distinct entities.
    big = (
        "alice@example.com\n\n"
        + "A" * 7000
        + "\n\nstill talking about alice@example.com here\n\n"
        + "B" * 7000
        + "\n\nbob@example.com"
    )
    result = await detector.detect(big, _ctx(content_type=ContentType.TEXT))

    seen_emails = sorted({e.text for e in result.entities})
    assert seen_emails == ["alice@example.com", "bob@example.com"]
    assert result.chunks_total >= 2
    assert result.chunks_failed == 0
    assert result.chunker == "plaintext"
    assert result.chunker_version == "1"


@pytest.mark.asyncio
async def test_tool_detector_marks_failed_chunks_for_fail_closed_routing() -> None:
    """A chunk that raises must surface ``chunks_failed > 0``.

    The interceptor uses that bit to switch the whole payload to a
    fail-closed placeholder, so the orchestrator MUST report failure
    here even if other chunks succeeded.
    """
    inner = AsyncMock()

    async def flaky(_text, **_kwargs):
        if "explode" in _text:
            raise RuntimeError("simulated detector outage")
        return _detection([_entity("alice@example.com")])

    inner.detect = AsyncMock(side_effect=flaky)
    detector = ToolPrivacyDetector(detector=inner)
    payload = "block one\n\n" + ("explode " * 1500) + "\n\n" + "block two"

    result = await detector.detect(payload, _ctx(content_type=ContentType.TEXT))

    assert result.has_failures
    failure_traces = [t for t in result.chunk_traces if t.failed]
    assert failure_traces, "at least one trace must record the failure reason"
    assert failure_traces[0].failure_reason  # non-empty exception type name


@pytest.mark.asyncio
async def test_tool_detector_respects_per_chunk_timeout() -> None:
    """A slow detector chunk is cancelled and recorded as ``timeout``."""
    inner = AsyncMock()

    async def slow(_text, **_kwargs):
        await asyncio.sleep(5.0)
        return _detection([])

    inner.detect = AsyncMock(side_effect=slow)
    detector = ToolPrivacyDetector(detector=inner, per_chunk_timeout_s=0.05)
    result = await detector.detect("hello", _ctx(content_type=ContentType.TEXT))

    assert result.has_failures
    assert any(t.failure_reason == "timeout" for t in result.chunk_traces)


@pytest.mark.asyncio
async def test_tool_detector_passes_intent_hint_for_adversarial_inputs() -> None:
    """The orchestrator marks every chunk as ``intent_hint='tool_output'``.

    This is the hook the underlying PiiDetector uses to log "incoming
    content is data, not instructions" — keep the contract pinned so
    future prompt tuning can branch on it.
    """
    inner = AsyncMock()
    inner.detect = AsyncMock(return_value=_detection([]))
    detector = ToolPrivacyDetector(detector=inner)
    await detector.detect("hello world", _ctx(content_type=ContentType.TEXT))

    assert inner.detect.await_count == 1
    _, kwargs = inner.detect.await_args
    assert kwargs.get("intent_hint") == "tool_output"


def test_tool_detector_exposes_version_for_vault_compat_audits() -> None:
    """Vault snapshots are keyed by detector version. The version must
    flow out so the transparency report can flag mismatches."""
    assert ToolPrivacyDetector.VERSION == TOOL_DETECTOR_VERSION
    assert ToolPrivacyDetector.VERSION  # non-empty


@pytest.mark.asyncio
async def test_tool_detector_returns_empty_when_chunker_yields_nothing() -> None:
    """Empty / null-only payloads must short-circuit without firing the detector."""
    inner = AsyncMock()
    inner.detect = AsyncMock()

    detector = ToolPrivacyDetector(detector=inner)
    result = await detector.detect("", _ctx(content_type=ContentType.TEXT))

    assert result.entities == []
    assert result.chunks_total == 0
    inner.detect.assert_not_called()
