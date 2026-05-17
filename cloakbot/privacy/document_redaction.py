"""User-uploaded document privacy pipeline.

Sibling of :mod:`visual_redaction`. Where the visual module handles
``image/*`` uploads via OCR + bbox detection, this module handles
``text/*`` uploads via the chunker-backed PII detector that A3
(:mod:`tests.eval.runners.long_doc_leak_eval`) measures end-to-end.

Both modules feed the same per-session vault, so a name detected in a
long uploaded contract gets the same placeholder as the same name
typed into the chat — that property is what makes the Local-vs-Remote
view in the WebUI work consistently across uploads, tool returns, and
follow-up turns.

This module intentionally stays thin: the heavy lifting
(chunking, per-chunk LLM detection, fail-closed merge) lives in
``sanitize_tool_output_chunked``. We wrap it with a stable
``user_upload:<name>`` tool name so privacy telemetry and any future
approval policy can distinguish user-uploaded documents from real
tool returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256

from cloakbot.privacy.core.detection.chunking.text import PlainTextChunker
from cloakbot.privacy.core.sanitization.sanitize import sanitize_tool_output_chunked

# Preview length surfaced to the WebUI alongside the full sanitized
# text. Frontend can opt to show the preview in compact UI and the full
# text in an expanded view; 400 chars is enough to be informative
# without choking a chat-bubble layout.
_PREVIEW_MAX_CHARS = 400


@dataclass(frozen=True)
class UserDocumentResult:
    """One user-uploaded document, after chunked PII redaction.

    The fields are designed to support a Local-vs-Remote toggle in the
    UI: ``sanitized_text`` is the remote-bound version, the frontend
    keeps the original locally (via a data URL it submitted, or via a
    vault artifact written by the channel layer). ``original_sha256``
    lets the frontend match the redaction record back to the upload
    it submitted, in case multiple documents are attached in one turn.
    """

    document_name: str | None
    mime_type: str
    original_sha256: str
    char_count: int
    sanitized_text: str
    sanitized_preview: str
    chunks_total: int
    chunks_failed: bool
    was_sanitized: bool
    entity_types: list[str] = field(default_factory=list)


async def process_user_document(
    text: str,
    *,
    session_key: str,
    turn_id: str,
    document_name: str | None = None,
    mime_type: str = "text/plain",
) -> UserDocumentResult:
    """Run chunker-backed PII detection over a user-uploaded document.

    The synthetic ``user_upload:<document_name>`` tool name is the
    only place where the upload is distinguishable from a real tool
    return; both share the chunker, the per-chunk failure handling,
    and the session vault.
    """
    label = document_name or "document"
    sanitized, modified, entities, chunks_failed = await sanitize_tool_output_chunked(
        text,
        session_key,
        tool_name=f"user_upload:{label}",
        turn_id=turn_id,
    )

    digest = sha256(text.encode("utf-8")).hexdigest()
    # The chunker runs inside ``sanitize_tool_output_chunked``, but its
    # chunk count isn't surfaced through the return signature. Recount
    # here so the WebUI report can show "this 8k-char contract split
    # into 2 chunks" without us having to thread chunker telemetry
    # through the sanitizer layer.
    chunks = PlainTextChunker().chunk(text)

    preview = (
        sanitized
        if len(sanitized) <= _PREVIEW_MAX_CHARS
        else sanitized[:_PREVIEW_MAX_CHARS] + "…"
    )

    return UserDocumentResult(
        document_name=document_name,
        mime_type=mime_type,
        original_sha256=digest,
        char_count=len(text),
        sanitized_text=sanitized,
        sanitized_preview=preview,
        chunks_total=len(chunks),
        chunks_failed=chunks_failed,
        was_sanitized=modified,
        entity_types=sorted({e.entity_type for e in entities}),
    )
