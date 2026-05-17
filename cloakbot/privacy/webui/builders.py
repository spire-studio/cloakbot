from __future__ import annotations

import base64
from pathlib import Path

from loguru import logger

from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.replay import build_turn_timeline
from cloakbot.privacy.transparency.report import build_session_privacy_snapshot
from cloakbot.privacy.webui.contracts import (
    WebUIPrivacyPayload,
    WebUIPrivacyTimeline,
    WebUIPrivacyTimelineEvent,
    WebUIPrivacyTurn,
    WebUIToolApproval,
    WebUIToolResult,
    WebUIUserAttachment,
    WebUIUserDocument,
)


def _build_user_attachments(ctx: TurnContext) -> list[WebUIUserAttachment]:
    """Pair each user-input visual redaction record with its vault artifact.

    The visual pipeline writes the redacted image to the per-session
    vault on disk; this reader pulls those bytes back, base64-encodes
    them, and emits one :class:`WebUIUserAttachment` per uploaded image.
    The pairing is positional — the pipeline appends to both lists in
    the same order — and we fall back to ``status="omitted"`` whenever a
    redaction record has no matching artifact (fail-closed image).
    """
    redactions = ctx.user_input_visual_redactions
    if not redactions:
        return []

    redacted_paths = [
        artifact.path
        for artifact in ctx.user_input_vault_artifacts
        if artifact.kind == "redacted_image"
    ]
    original_paths = [
        artifact.path
        for artifact in ctx.user_input_vault_artifacts
        if artifact.kind == "original_image"
    ]

    attachments: list[WebUIUserAttachment] = []
    redacted_cursor = 0
    original_cursor = 0
    for redaction in redactions:
        is_redacted = redaction.status == "redacted"
        redacted_data_url: str | None = None
        original_data_url: str | None = None
        if is_redacted and redacted_cursor < len(redacted_paths):
            redacted_data_url = _file_to_data_url(redacted_paths[redacted_cursor])
            redacted_cursor += 1
        if original_cursor < len(original_paths):
            original_data_url = _file_to_data_url(original_paths[original_cursor])
            original_cursor += 1
        attachments.append(
            WebUIUserAttachment(
                status="redacted" if is_redacted and redacted_data_url else "omitted",
                originalDataUrl=original_data_url,
                redactedDataUrl=redacted_data_url,
                redaction=redaction,
                reason=redaction.reason,
            )
        )
    return attachments


def _build_user_documents(ctx: TurnContext) -> list[WebUIUserDocument]:
    """Pair each redacted document result with the original text vault artifact.

    Pipeline writes the original document text to the per-session
    vault BEFORE running the chunker so we can echo the user's true
    upload back into the Local view. We pair the lists positionally —
    the pipeline appends to both in the same order — and fall back to
    ``original_text=None`` whenever the vault read fails, so the
    frontend can render the sanitized version even if the original
    artifact has been pruned.
    """
    results = ctx.user_input_documents
    if not results:
        return []

    original_paths = [
        artifact.path
        for artifact in ctx.user_input_document_artifacts
        if artifact.kind == "original_document"
    ]

    documents: list[WebUIUserDocument] = []
    for index, result in enumerate(results):
        original_text: str | None = None
        if index < len(original_paths):
            original_text = _file_to_text(original_paths[index])
        documents.append(
            WebUIUserDocument(
                documentName=result.document_name,
                mimeType=result.mime_type,
                originalSha256=result.original_sha256,
                charCount=result.char_count,
                originalText=original_text,
                sanitizedText=result.sanitized_text,
                sanitizedPreview=result.sanitized_preview,
                chunksTotal=result.chunks_total,
                chunksFailed=result.chunks_failed,
                wasSanitized=result.was_sanitized,
                entityTypes=list(result.entity_types),
            )
        )
    return documents


def _file_to_text(path: str) -> str | None:
    """Read a vault text artifact off disk.

    Mirrors :func:`_file_to_data_url` but for plain-text uploads,
    where we want the raw string (not a data URL) so the WebUI can
    render the document inline in a chat bubble. Returns ``None`` on
    IO failure so the caller falls back to "original unavailable".
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning(
            "failed to read vault document artifact for webui payload: {} ({})",
            path,
            exc,
        )
        return None


def _file_to_data_url(path: str) -> str | None:
    """Read a vault artifact off disk and inline it as a base64 data URL.

    Returns ``None`` on any IO/encoding failure — the caller treats
    that as "omitted" so the frontend never tries to render a partial
    file. Mime is inferred from the suffix because the vault saves
    files with stable extensions (``.png`` / ``.jpg`` / ``.webp``).
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        logger.warning("failed to read vault artifact for webui payload: {} ({})", path, exc)
        return None
    suffix = Path(path).suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def build_webui_privacy_turn(ctx: TurnContext) -> WebUIPrivacyTurn:
    return WebUIPrivacyTurn(
        turn_id=ctx.turn_id,
        intent=ctx.intent.value,
        remote_prompt=ctx.sanitized_input,
        local_computations=ctx.local_computations,
        userAttachments=_build_user_attachments(ctx),
        userDocuments=_build_user_documents(ctx),
        tool_results=[
            WebUIToolResult(
                tool_call_id=result.tool_call_id,
                tool_name=result.tool_name,
                remote_arguments=result.remote_arguments,
                sanitized_output=result.sanitized_output,
                was_sanitized=result.was_sanitized,
                visual_redactions=result.visual_redactions,
            )
            for result in ctx.tool_results
        ],
        tool_approvals=[
            WebUIToolApproval(
                approval_id=approval.approval_id,
                tool_call_id=approval.tool_call_id,
                tool_name=approval.tool_name,
                privacy_class=approval.privacy_class,
                remote_arguments=approval.remote_arguments,
                restored_arguments=approval.restored_arguments,
                detected_entities=approval.detected_entities,
                status=approval.status,
            )
            for approval in ctx.tool_approvals
        ],
    )


def build_webui_privacy_timeline(session_key: str, ctx: TurnContext) -> WebUIPrivacyTimeline:
    timeline = build_turn_timeline(session_key, ctx.turn_id)
    return WebUIPrivacyTimeline(
        turn_id=ctx.turn_id,
        trace_id=timeline.trace_id,
        total_duration_ms=timeline.total_duration_ms,
        stage_durations_ms=timeline.stage_durations_ms,
        events=[
            WebUIPrivacyTimelineEvent(
                event_type=event.event_type.value,
                sequence=event.sequence,
                stage=event.stage.value,
                status=event.status.value,
                span_id=event.span_id,
                parent_span_id=event.parent_span_id,
                timestamp=event.timestamp,
                duration_ms=event.duration_ms,
                payload=event.payload,
            )
            for event in timeline.events
        ],
    )


def build_webui_privacy_payload(session_key: str, ctx: TurnContext) -> WebUIPrivacyPayload:
    return WebUIPrivacyPayload(
        privacy=build_session_privacy_snapshot(session_key),
        privacy_annotations=ctx.display_output_annotations,
        privacy_turn=build_webui_privacy_turn(ctx),
        privacy_timeline=build_webui_privacy_timeline(session_key, ctx),
    )
