"""Cap F — WebUI privacy side-channel + the BLOCKING localhost gate.

The #1 risk in the whole rebase: re-homing the raw-value-bearing privacy payload
onto upstream's gateway (which supports remote, token-authed connections) must not
egress the cleartext vault to a non-localhost client. These tests pin:

- the redacted projection strips every raw-bearing field for non-localhost,
- localhost gets the full payload (round-trip),
- the same gate applies to the _agent_ui merge, the standalone frames, the HTTP
  history route, and the tool-approval authorization,
- the blocking acceptance test: a non-localhost client receives zero raw entity
  values / original images / original documents / restored arguments.
"""

from __future__ import annotations

import json

import pytest

from cloakbot.bus.events import OUTBOUND_META_AGENT_UI
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.core.types import GeneralEntity, Severity
from cloakbot.privacy.tool_models import ToolApprovalStatus
from cloakbot.privacy.transparency.report import (
    EntitySummary,
    SessionEntityData,
    SessionPrivacySnapshot,
)
from cloakbot.privacy.visual_redaction import VisualPrivacyRedaction
from cloakbot.privacy.webui.contracts import (
    WebUIPrivacyPayload,
    WebUIPrivacyTimeline,
    WebUIPrivacyTurn,
    WebUIToolApproval,
    WebUIToolResult,
    WebUIUserAttachment,
    WebUIUserDocument,
)
from cloakbot.privacy.webui.side_channel import (
    _REDACTED_SENTINEL,
    AGENT_UI_PRIVACY_KEY,
    merge_privacy_into_agent_ui,
    privacy_side_channel_frames,
    privacy_snapshot_frame,
    privacy_trace_frame,
    project_payload_for_egress,
    project_snapshot_for_egress,
    project_tool_approval_for_egress,
    tool_approval_frame,
)
from cloakbot.tool_privacy import ToolPrivacyClass

# Raw values that must NEVER cross to a non-localhost client.
RAW_NAME = "Alice Chen"
RAW_ALIAS = "Alice"
RAW_DOC_TEXT = "SSN: 123-45-6789 belongs to Alice Chen"
RAW_IMAGE_URL = "data:image/png;base64,RAWORIGINALIMAGEBYTES=="
RAW_RESTORED_ARG = {"to": "alice.chen@example.com", "subject": "raw secret"}
RAW_ENTITY_TEXT = "Alice Chen lives at 1 Raw Street"
RAW_ANNOTATION_TEXT = "Alice Chen"


def _snapshot() -> SessionPrivacySnapshot:
    return SessionPrivacySnapshot(
        total_entities=1,
        entities=[
            SessionEntityData(
                placeholder="<<PERSON_1>>",
                entity_type="PERSON",
                severity=Severity.HIGH,
                canonical=RAW_NAME,
                aliases=[RAW_ALIAS],
                value=RAW_NAME,
                created_turn="turn-1",
                last_seen_turn="turn-1",
            )
        ],
        entity_counts=[EntitySummary(entity_type="PERSON", severity=Severity.HIGH, count=1)],
    )


def _annotation() -> RestoredTokenAnnotation:
    return RestoredTokenAnnotation(
        placeholder="<<PERSON_1>>",
        text=RAW_ANNOTATION_TEXT,
        start=3,
        end=13,
        entity_type="PERSON",
        severity=Severity.HIGH,
        canonical=RAW_NAME,
        aliases=[RAW_ALIAS],
        value=RAW_NAME,
        formula="x + y",
    )


def _tool_approval() -> WebUIToolApproval:
    return WebUIToolApproval(
        approvalId="appr-1",
        toolCallId="call-1",
        toolName="send_email",
        privacyClass=ToolPrivacyClass.EXTERNAL,
        remoteArguments={"to": "<<EMAIL_1>>", "subject": "<<TEXT_1>>"},
        restoredArguments=RAW_RESTORED_ARG,
        detectedEntities=[GeneralEntity(text=RAW_ENTITY_TEXT, entity_type="PERSON")],
        status=ToolApprovalStatus.PENDING,
    )


def _attachment() -> WebUIUserAttachment:
    return WebUIUserAttachment(
        status="redacted",
        originalDataUrl=RAW_IMAGE_URL,
        redactedDataUrl="data:image/png;base64,REDACTEDOK==",
        redaction=VisualPrivacyRedaction(
            sourcePath="/tmp/x.png",
            status="redacted",
            detectedItems=1,
            redactionBoxes=1,
            labels=["name"],
        ),
        reason=None,
    )


def _document() -> WebUIUserDocument:
    return WebUIUserDocument(
        documentName="notes.txt",
        mimeType="text/plain",
        originalSha256="abc123",
        charCount=42,
        originalText=RAW_DOC_TEXT,
        sanitizedText="SSN: <<US_SSN_1>> belongs to <<PERSON_1>>",
        sanitizedPreview="SSN: <<US_SSN_1>> ...",
        chunksTotal=1,
        chunksFailed=False,
        wasSanitized=True,
        entityTypes=["US_SSN", "PERSON"],
    )


def _payload() -> WebUIPrivacyPayload:
    return WebUIPrivacyPayload(
        privacy=_snapshot(),
        privacyAnnotations=[_annotation()],
        privacyTurn=WebUIPrivacyTurn(
            turnId="turn-1",
            intent="chat",
            remotePrompt="hello <<PERSON_1>>",
            localComputations=[],
            toolResults=[
                WebUIToolResult(
                    toolCallId="call-r",
                    toolName="read_file",
                    remoteArguments={"path": "<<PRIVATE_URL_1>>"},
                    sanitizedOutput="Owner: <<PERSON_1>>",
                    wasSanitized=True,
                )
            ],
            toolApprovals=[_tool_approval()],
            userAttachments=[_attachment()],
            userDocuments=[_document()],
        ),
        privacyTimeline=WebUIPrivacyTimeline(
            turnId="turn-1",
            traceId="trace-1",
            totalDurationMs=5,
            stageDurationsMs={"sanitized": 5},
            events=[],
        ),
    )


def _all_raw_values() -> list[str]:
    return [RAW_NAME, RAW_ALIAS, RAW_DOC_TEXT, RAW_IMAGE_URL, RAW_ENTITY_TEXT]


def _assert_no_raw(blob: object) -> None:
    """Assert the serialized blob contains none of the raw cleartext values."""
    text = json.dumps(blob, ensure_ascii=False)
    for raw in _all_raw_values():
        assert raw not in text, f"raw value leaked into projection: {raw!r}"
    # restored args contains the raw email + subject
    assert "alice.chen@example.com" not in text
    assert "raw secret" not in text


# ---------------------------------------------------------------------------
# Round-trip: localhost gets the full payload verbatim
# ---------------------------------------------------------------------------


def test_localhost_receives_full_payload_unchanged() -> None:
    payload = _payload()
    projected = project_payload_for_egress(payload, is_localhost=True)
    # Same object identity — no copy, no strip.
    assert projected is payload
    text = json.dumps(projected.model_dump(mode="json", by_alias=True), ensure_ascii=False)
    for raw in _all_raw_values():
        assert raw in text


def test_localhost_roundtrip_through_agent_ui_merge() -> None:
    payload = _payload()
    metadata: dict = {}
    merge_privacy_into_agent_ui(metadata, payload, is_localhost=True)
    blob = metadata[OUTBOUND_META_AGENT_UI][AGENT_UI_PRIVACY_KEY]
    # Re-validate the round-tripped blob back into the contract.
    restored = WebUIPrivacyPayload.model_validate(blob)
    assert restored.privacy.entities[0].canonical == RAW_NAME
    assert restored.privacy_turn.tool_approvals[0].restored_arguments == RAW_RESTORED_ARG
    assert restored.privacy_turn.user_attachments[0].original_data_url == RAW_IMAGE_URL
    assert restored.privacy_turn.user_documents[0].original_text == RAW_DOC_TEXT


# ---------------------------------------------------------------------------
# BLOCKING INVARIANT: non-localhost receives the redacted projection only
# ---------------------------------------------------------------------------


def test_blocking_non_localhost_payload_has_zero_raw_values() -> None:
    """THE blocking acceptance test for the whole rebase."""
    payload = _payload()
    projected = project_payload_for_egress(payload, is_localhost=False)
    blob = projected.model_dump(mode="json", by_alias=True)
    _assert_no_raw(blob)


def test_non_localhost_snapshot_strips_value_canonical_aliases() -> None:
    projected = project_snapshot_for_egress(_snapshot(), is_localhost=False)
    entity = projected.entities[0]
    assert entity.placeholder == "<<PERSON_1>>"  # placeholder kept
    assert entity.entity_type == "PERSON"  # type kept
    assert entity.severity == Severity.HIGH  # severity kept
    assert entity.value is None
    assert entity.aliases == []
    assert entity.canonical == _REDACTED_SENTINEL
    # counts (types/severities/counts only) survive
    assert projected.entity_counts[0].count == 1


def test_non_localhost_annotation_strips_restored_text() -> None:
    projected = project_payload_for_egress(_payload(), is_localhost=False)
    ann = projected.privacy_annotations[0]
    assert ann.placeholder == "<<PERSON_1>>"
    assert ann.start == 3 and ann.end == 13  # offsets preserved for UI badge
    assert ann.text == _REDACTED_SENTINEL
    assert ann.canonical == _REDACTED_SENTINEL
    assert ann.value is None
    assert ann.formula is None
    assert ann.aliases == []


def test_non_localhost_tool_approval_strips_restored_args_and_entities() -> None:
    projected = project_tool_approval_for_egress(_tool_approval(), is_localhost=False)
    assert projected.approval_id == "appr-1"  # identity kept
    assert projected.remote_arguments == {"to": "<<EMAIL_1>>", "subject": "<<TEXT_1>>"}
    assert projected.restored_arguments == {}
    assert projected.detected_entities == []
    assert projected.status == ToolApprovalStatus.PENDING


def test_non_localhost_attachment_drops_original_image() -> None:
    projected = project_payload_for_egress(_payload(), is_localhost=False)
    att = projected.privacy_turn.user_attachments[0]
    assert att.original_data_url is None
    assert att.redacted_data_url == "data:image/png;base64,REDACTEDOK=="  # redacted kept
    assert att.status == "redacted"


def test_non_localhost_document_drops_original_text() -> None:
    projected = project_payload_for_egress(_payload(), is_localhost=False)
    doc = projected.privacy_turn.user_documents[0]
    assert doc.original_text is None
    assert doc.sanitized_text == "SSN: <<US_SSN_1>> belongs to <<PERSON_1>>"  # sanitized kept
    assert doc.entity_types == ["US_SSN", "PERSON"]  # types kept


def test_non_localhost_remote_prompt_and_tool_output_preserved() -> None:
    """Already-placeholdered fields are safe and must stay (they are the point)."""
    projected = project_payload_for_egress(_payload(), is_localhost=False)
    assert projected.privacy_turn.remote_prompt == "hello <<PERSON_1>>"
    assert projected.privacy_turn.tool_results[0].sanitized_output == "Owner: <<PERSON_1>>"


# ---------------------------------------------------------------------------
# Gate applied in every emission helper (the three paths share one chokepoint)
# ---------------------------------------------------------------------------


def test_agent_ui_merge_gates_non_localhost() -> None:
    metadata: dict = {}
    merge_privacy_into_agent_ui(metadata, _payload(), is_localhost=False)
    _assert_no_raw(metadata[OUTBOUND_META_AGENT_UI][AGENT_UI_PRIVACY_KEY])


def test_agent_ui_merge_preserves_existing_agent_ui_keys() -> None:
    metadata: dict = {OUTBOUND_META_AGENT_UI: {"kind": "panel", "data": {"x": 1}}}
    merge_privacy_into_agent_ui(metadata, _payload(), is_localhost=True)
    blob = metadata[OUTBOUND_META_AGENT_UI]
    assert blob["kind"] == "panel"  # existing keys untouched
    assert AGENT_UI_PRIVACY_KEY in blob


@pytest.mark.parametrize(
    "frame_builder",
    [privacy_snapshot_frame, privacy_trace_frame, tool_approval_frame],
)
def test_standalone_frames_gate_non_localhost(frame_builder) -> None:
    if frame_builder is privacy_snapshot_frame:
        frame = frame_builder(_snapshot(), is_localhost=False)
    elif frame_builder is tool_approval_frame:
        frame = frame_builder(_tool_approval(), is_localhost=False)
    else:
        frame = frame_builder(_payload(), is_localhost=False)
    _assert_no_raw(frame)


def test_side_channel_frames_localhost_carry_raw_values() -> None:
    frames = privacy_side_channel_frames(_payload(), is_localhost=True)
    events = {f["event"] for f in frames}
    assert events == {"privacy_snapshot", "privacy_trace", "tool_approval"}
    text = json.dumps(frames, ensure_ascii=False)
    assert RAW_NAME in text  # localhost gets the cleartext


def test_side_channel_frames_non_localhost_zero_raw() -> None:
    frames = privacy_side_channel_frames(_payload(), is_localhost=False)
    # one snapshot + one trace + one approval (the turn has one pending approval)
    assert sum(1 for f in frames if f["event"] == "tool_approval") == 1
    _assert_no_raw(frames)
