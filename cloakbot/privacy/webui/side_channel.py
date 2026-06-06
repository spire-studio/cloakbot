"""WebUI privacy side-channel: payload → ``_agent_ui.privacy`` + standalone frames.

This module re-homes the bespoke ``channels/webui.py`` privacy emission onto
upstream's gateway (``channels/websocket.py``). It is pure transformation logic
with **no** transport concern, so it can be unit-tested without a socket:

- :func:`merge_privacy_into_agent_ui` folds a :class:`WebUIPrivacyPayload`
  (``by_alias``) under ``metadata["_agent_ui"]["privacy"]`` so upstream's
  existing ``agent_ui`` passthrough forwards it inside ``message`` /
  ``assistant_done`` frames — zero channel fork.
- :func:`privacy_side_channel_frames` produces the standalone
  ``privacy_snapshot`` / ``privacy_trace`` / ``tool_approval`` event frames.

The **blocking localhost gate** lives here as :func:`project_payload_for_egress`:
non-localhost connections must never receive the raw-bearing fields
(``SessionEntityData.{value,canonical,aliases}``,
``WebUIToolApproval.restoredArguments``,
``WebUIUserAttachment.originalDataUrl``,
``WebUIUserDocument.originalText``,
``RestoredTokenAnnotation.{text,value,canonical,formula}``). The projection keeps
placeholders + entity types/severities/counts only. The gate is applied at the
SAME chokepoint in all three egress paths (WS frame, HTTP route, tool approval)
by passing ``is_localhost`` through every public function below.
"""

from __future__ import annotations

from typing import Any

from cloakbot.bus.events import OUTBOUND_META_AGENT_UI
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.transparency.report import (
    SessionEntityData,
    SessionPrivacySnapshot,
)
from cloakbot.privacy.webui.contracts import (
    WebUIPrivacyPayload,
    WebUIPrivacyTurn,
    WebUIToolApproval,
    WebUIUserAttachment,
    WebUIUserDocument,
)

# Key under ``_agent_ui`` where the privacy blob rides upstream passthrough.
AGENT_UI_PRIVACY_KEY = "privacy"

# Placeholder substituted for any raw value stripped by the egress gate, so a
# non-localhost client can still render a "value withheld" affordance without
# ever learning the cleartext.
_REDACTED_SENTINEL = "[redacted: localhost-only]"


# ---------------------------------------------------------------------------
# Blocking localhost gate — redacted projection
# ---------------------------------------------------------------------------


def _redact_entity(entity: SessionEntityData) -> SessionEntityData:
    """Strip raw-bearing fields from one session entity.

    Keeps ``placeholder`` + ``entity_type`` + ``severity`` + turn bookkeeping
    (all non-sensitive) and drops ``canonical`` / ``aliases`` / ``value``.
    """
    return SessionEntityData(
        placeholder=entity.placeholder,
        entity_type=entity.entity_type,
        severity=entity.severity,
        canonical=_REDACTED_SENTINEL,
        aliases=[],
        value=None,
        created_turn=entity.created_turn,
        last_seen_turn=entity.last_seen_turn,
    )


def _redact_snapshot(snapshot: SessionPrivacySnapshot) -> SessionPrivacySnapshot:
    """Return a snapshot with every entity's raw value stripped.

    ``entity_counts`` is types/severities/counts only — already safe — so it is
    preserved verbatim; only per-entity raw values are removed.
    """
    return SessionPrivacySnapshot(
        total_entities=snapshot.total_entities,
        entities=[_redact_entity(e) for e in snapshot.entities],
        entity_counts=list(snapshot.entity_counts),
    )


def _redact_annotation(annotation: RestoredTokenAnnotation) -> RestoredTokenAnnotation:
    """Strip the restored cleartext from one display annotation.

    ``text`` / ``value`` / ``canonical`` / ``formula`` all carry raw values; the
    placeholder, span offsets, type and severity stay so the overlay can still
    badge the restored span position without revealing what it restored to.
    """
    return RestoredTokenAnnotation(
        annotation_type=annotation.annotation_type,
        placeholder=annotation.placeholder,
        text=_REDACTED_SENTINEL,
        start=annotation.start,
        end=annotation.end,
        entity_type=annotation.entity_type,
        severity=annotation.severity,
        canonical=_REDACTED_SENTINEL,
        aliases=[],
        value=None,
        formula=None,
    )


def _redact_tool_approval(approval: WebUIToolApproval) -> WebUIToolApproval:
    """Strip the locally-restored arguments from one tool approval.

    ``restored_arguments`` is the cleartext the model would run against; the
    ``remote_arguments`` (already placeholdered) plus identifiers, class and
    status stay so a remote viewer can see *that* an approval is pending without
    the underlying secrets. ``detected_entities`` is dropped (it carries the raw
    matched text / value).
    """
    return WebUIToolApproval(
        approvalId=approval.approval_id,
        toolCallId=approval.tool_call_id,
        toolName=approval.tool_name,
        privacyClass=approval.privacy_class,
        remoteArguments=approval.remote_arguments,
        restoredArguments={},
        detectedEntities=[],
        status=approval.status,
    )


def _redact_attachment(attachment: WebUIUserAttachment) -> WebUIUserAttachment:
    """Drop the original (un-redacted) image data URL from one attachment.

    Keeps the redacted artifact, status, redaction record and reason; only
    ``original_data_url`` (the raw image) is removed.
    """
    return WebUIUserAttachment(
        status=attachment.status,
        originalDataUrl=None,
        redactedDataUrl=attachment.redacted_data_url,
        redaction=attachment.redaction,
        reason=attachment.reason,
    )


def _redact_document(document: WebUIUserDocument) -> WebUIUserDocument:
    """Drop the original (un-sanitized) text from one user document.

    Keeps the sanitized text/preview, hashes, counts and entity *types*; only
    ``original_text`` (the raw upload) is removed.
    """
    return WebUIUserDocument(
        documentName=document.document_name,
        mimeType=document.mime_type,
        originalSha256=document.original_sha256,
        charCount=document.char_count,
        originalText=None,
        sanitizedText=document.sanitized_text,
        sanitizedPreview=document.sanitized_preview,
        chunksTotal=document.chunks_total,
        chunksFailed=document.chunks_failed,
        wasSanitized=document.was_sanitized,
        entityTypes=list(document.entity_types),
    )


def _redact_turn(turn: WebUIPrivacyTurn) -> WebUIPrivacyTurn:
    """Strip every raw-bearing field from one privacy turn.

    ``remote_prompt`` is already the placeholdered prompt (what the remote LLM
    saw), and ``tool_results.sanitized_output`` is post-sanitization — both safe.
    The raw surfaces are the approvals' restored args, the attachments' original
    images, and the documents' original text.
    """
    return WebUIPrivacyTurn(
        turnId=turn.turn_id,
        intent=turn.intent,
        remotePrompt=turn.remote_prompt,
        localComputations=list(turn.local_computations),
        toolResults=list(turn.tool_results),
        toolApprovals=[_redact_tool_approval(a) for a in turn.tool_approvals],
        userAttachments=[_redact_attachment(a) for a in turn.user_attachments],
        userDocuments=[_redact_document(d) for d in turn.user_documents],
    )


def project_payload_for_egress(
    payload: WebUIPrivacyPayload,
    *,
    is_localhost: bool,
) -> WebUIPrivacyPayload:
    """Apply the blocking localhost gate to a full privacy payload.

    Localhost connections receive the payload verbatim (the Privacy Inspector's
    whole purpose is the placeholder ↔ real-value diff). Any non-localhost
    connection receives a **redacted projection**: placeholders + entity
    types/severities/counts only, with every raw value, original image, original
    document and restored argument stripped.

    This is the single chokepoint the WS frame, the HTTP route and the
    tool-approval authorization all funnel through, so the three paths cannot
    drift apart.
    """
    if is_localhost:
        return payload
    return WebUIPrivacyPayload(
        privacy=_redact_snapshot(payload.privacy),
        privacyAnnotations=[_redact_annotation(a) for a in payload.privacy_annotations],
        privacyTurn=_redact_turn(payload.privacy_turn),
        privacyTimeline=payload.privacy_timeline,
    )


def project_tool_approval_for_egress(
    approval: WebUIToolApproval,
    *,
    is_localhost: bool,
) -> WebUIToolApproval:
    """Gate a standalone tool-approval prompt (same redaction as in a payload)."""
    if is_localhost:
        return approval
    return _redact_tool_approval(approval)


def project_snapshot_for_egress(
    snapshot: SessionPrivacySnapshot,
    *,
    is_localhost: bool,
) -> SessionPrivacySnapshot:
    """Gate a standalone session snapshot (same redaction as in a payload)."""
    if is_localhost:
        return snapshot
    return _redact_snapshot(snapshot)


# ---------------------------------------------------------------------------
# Emission helpers
# ---------------------------------------------------------------------------


def merge_privacy_into_agent_ui(
    metadata: dict[str, Any],
    payload: WebUIPrivacyPayload,
    *,
    is_localhost: bool,
) -> dict[str, Any]:
    """Fold *payload* under ``metadata["_agent_ui"]["privacy"]`` (gated).

    Returns the same ``metadata`` dict (mutated in place) so upstream's existing
    ``agent_ui`` passthrough in ``channels/websocket.py`` forwards the blob
    inside ``message`` / ``assistant_done`` frames with **zero** channel fork.
    The localhost gate is applied before serialization, so a non-localhost
    client never receives raw values even though it shares the socket.
    """
    projected = project_payload_for_egress(payload, is_localhost=is_localhost)
    agent_ui = metadata.get(OUTBOUND_META_AGENT_UI)
    if not isinstance(agent_ui, dict):
        agent_ui = {}
    agent_ui[AGENT_UI_PRIVACY_KEY] = projected.model_dump(mode="json", by_alias=True)
    metadata[OUTBOUND_META_AGENT_UI] = agent_ui
    return metadata


def privacy_snapshot_frame(
    snapshot: SessionPrivacySnapshot,
    *,
    is_localhost: bool,
) -> dict[str, Any]:
    """Build a standalone ``privacy_snapshot`` event frame (gated)."""
    projected = project_snapshot_for_egress(snapshot, is_localhost=is_localhost)
    return {
        "event": "privacy_snapshot",
        "data": projected.model_dump(mode="json", by_alias=True),
    }


def privacy_trace_frame(
    payload: WebUIPrivacyPayload,
    *,
    is_localhost: bool,
) -> dict[str, Any]:
    """Build a standalone ``privacy_trace`` event frame (gated).

    The trace carries the per-turn timeline plus the (gated) turn breakdown so
    the overlay's pipeline view can render without waiting for the next
    ``assistant_done``.
    """
    projected = project_payload_for_egress(payload, is_localhost=is_localhost)
    return {
        "event": "privacy_trace",
        "turn": projected.privacy_turn.model_dump(mode="json", by_alias=True),
        "timeline": projected.privacy_timeline.model_dump(mode="json", by_alias=True),
    }


def tool_approval_frame(
    approval: WebUIToolApproval,
    *,
    is_localhost: bool,
) -> dict[str, Any]:
    """Build a standalone ``tool_approval`` event frame (gated)."""
    projected = project_tool_approval_for_egress(approval, is_localhost=is_localhost)
    return {
        "event": "tool_approval",
        "approval": projected.model_dump(mode="json", by_alias=True),
    }


def privacy_side_channel_frames(
    payload: WebUIPrivacyPayload,
    *,
    is_localhost: bool,
    include_snapshot: bool = True,
    include_trace: bool = True,
) -> list[dict[str, Any]]:
    """Produce the standalone privacy frames for one finished turn (all gated).

    Tool-approval frames are emitted per pending approval carried on the turn.
    """
    frames: list[dict[str, Any]] = []
    if include_snapshot:
        frames.append(privacy_snapshot_frame(payload.privacy, is_localhost=is_localhost))
    if include_trace:
        frames.append(privacy_trace_frame(payload, is_localhost=is_localhost))
    for approval in payload.privacy_turn.tool_approvals:
        frames.append(tool_approval_frame(approval, is_localhost=is_localhost))
    return frames
