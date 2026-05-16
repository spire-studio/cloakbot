"""Tests for the user-uploaded document privacy pipeline.

Locks in the wrapper contract: ``process_user_document`` must call the
chunker-backed sanitizer with a ``user_upload:<name>`` tool name so
telemetry can distinguish user uploads from real tool returns, and the
returned :class:`UserDocumentResult` must carry the original SHA256,
the chunk count, the preview, and the detected entity-type set.

These tests intentionally mock ``sanitize_tool_output_chunked`` —
end-to-end behaviour through the real chunker is already covered by
``tests/eval/runners/long_doc_leak_eval.py`` (A3).
"""

from __future__ import annotations

from hashlib import sha256
from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.core.types import GeneralEntity
from cloakbot.privacy.document_redaction import (
    UserDocumentResult,
    process_user_document,
)


def _entity(text: str, etype: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=etype)


@pytest.mark.asyncio
async def test_process_user_document_forwards_user_upload_tool_name() -> None:
    """The wrapper must tag the chunker call with ``user_upload:<name>``."""
    fake_sanitize = AsyncMock(return_value=("sanitized body", True, [], False))
    with patch(
        "cloakbot.privacy.document_redaction.sanitize_tool_output_chunked",
        fake_sanitize,
    ):
        await process_user_document(
            "some long text",
            session_key="session-x",
            turn_id="turn-1",
            document_name="contract.txt",
            mime_type="text/plain",
        )

    fake_sanitize.assert_awaited_once()
    kwargs = fake_sanitize.await_args.kwargs
    assert kwargs["tool_name"] == "user_upload:contract.txt"
    assert kwargs["turn_id"] == "turn-1"
    args = fake_sanitize.await_args.args
    assert args[0] == "some long text"
    assert args[1] == "session-x"


@pytest.mark.asyncio
async def test_process_user_document_returns_full_result_shape() -> None:
    """All public fields on ``UserDocumentResult`` must be populated."""
    text = "hello there, my name is Megan and my phone is 555-1234."
    fake_sanitize = AsyncMock(
        return_value=(
            "hello there, my name is <<PERSON_1>> and my phone is <<PHONE_1>>.",
            True,
            [_entity("Megan", "person"), _entity("555-1234", "phone")],
            False,
        ),
    )
    with patch(
        "cloakbot.privacy.document_redaction.sanitize_tool_output_chunked",
        fake_sanitize,
    ):
        result = await process_user_document(
            text,
            session_key="session-x",
            turn_id="turn-1",
            document_name="memo.md",
            mime_type="text/markdown",
        )

    assert isinstance(result, UserDocumentResult)
    assert result.document_name == "memo.md"
    assert result.mime_type == "text/markdown"
    assert result.char_count == len(text)
    assert result.original_sha256 == sha256(text.encode("utf-8")).hexdigest()
    assert result.sanitized_text.startswith("hello there, my name is <<PERSON_1>>")
    assert result.sanitized_preview == result.sanitized_text  # short enough; no ellipsis
    assert result.chunks_total >= 1
    assert result.chunks_failed is False
    assert result.was_sanitized is True
    assert result.entity_types == ["person", "phone"]


@pytest.mark.asyncio
async def test_process_user_document_truncates_long_preview() -> None:
    """Preview must be clipped at 400 chars with a trailing ellipsis."""
    long_sanitized = "a" * 500
    fake_sanitize = AsyncMock(return_value=(long_sanitized, False, [], False))
    with patch(
        "cloakbot.privacy.document_redaction.sanitize_tool_output_chunked",
        fake_sanitize,
    ):
        result = await process_user_document(
            "any source text",
            session_key="session-x",
            turn_id="turn-1",
        )

    # Full text retained; preview clipped at the 400-char boundary.
    assert result.sanitized_text == long_sanitized
    assert len(result.sanitized_preview) == 401  # 400 + ellipsis
    assert result.sanitized_preview.endswith("…")
    # Default name fallback when caller omits document_name.
    assert result.document_name is None


@pytest.mark.asyncio
async def test_process_user_document_counts_multiple_chunks() -> None:
    """A payload exceeding the default chunker budget must report >1 chunks."""
    # Default plaintext chunker max_chars=6000; 13k chars → at least 2 chunks.
    text = "X " * 7_000
    fake_sanitize = AsyncMock(return_value=("sanitized", True, [], False))
    with patch(
        "cloakbot.privacy.document_redaction.sanitize_tool_output_chunked",
        fake_sanitize,
    ):
        result = await process_user_document(
            text,
            session_key="session-x",
            turn_id="turn-1",
        )

    assert result.chunks_total >= 2


@pytest.mark.asyncio
async def test_process_user_document_propagates_chunks_failed() -> None:
    """``chunks_failed`` on the underlying sanitizer must surface to the result."""
    fake_sanitize = AsyncMock(return_value=("sanitized", True, [], True))
    with patch(
        "cloakbot.privacy.document_redaction.sanitize_tool_output_chunked",
        fake_sanitize,
    ):
        result = await process_user_document(
            "some text",
            session_key="session-x",
            turn_id="turn-1",
        )

    assert result.chunks_failed is True
