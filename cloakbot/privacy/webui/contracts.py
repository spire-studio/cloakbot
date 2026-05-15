from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.core.types import DetectedEntity
from cloakbot.privacy.tool_models import ToolApprovalStatus
from cloakbot.privacy.transparency.report import SessionPrivacySnapshot
from cloakbot.privacy.visual_redaction import VisualPrivacyRedaction
from cloakbot.tool_privacy import ToolPrivacyClass

WEBUI_PRIVACY_METADATA_KEY = "webuiPrivacy"


class WebUIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WebUIAttachment(WebUIModel):
    """One image attachment sent inline with a user message.

    ``data_url`` is the full ``data:<mime>;base64,<payload>`` form so the
    visual privacy pipeline can decode it without filesystem access.
    Frontend keeps the original copy locally — the same data URL is not
    echoed back from the server, which prevents an accidental round-trip
    that would defeat the redaction.
    """

    mime_type: str = Field(alias="mimeType")
    data_url: str = Field(alias="dataUrl")
    name: str | None = None


class WebUIUserMessage(WebUIModel):
    type: Literal["message", "tool_approval"] = "message"
    content: str = ""
    attachments: list[WebUIAttachment] = Field(default_factory=list)
    approval_id: str | None = Field(default=None, alias="approvalId")
    approved: bool = True


class WebUIStatusData(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    ready: bool
    frontend_built: bool = Field(alias="frontendBuilt")


class WebUIToolResult(WebUIModel):
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    remote_arguments: dict[str, Any] = Field(alias="remoteArguments")
    sanitized_output: str = Field(alias="sanitizedOutput")
    was_sanitized: bool = Field(alias="wasSanitized")
    visual_redactions: list[VisualPrivacyRedaction] = Field(default_factory=list, alias="visualRedactions")


class WebUIToolApproval(WebUIModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    approval_id: str = Field(alias="approvalId")
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    privacy_class: ToolPrivacyClass = Field(alias="privacyClass")
    remote_arguments: dict[str, Any] = Field(alias="remoteArguments")
    restored_arguments: dict[str, Any] = Field(alias="restoredArguments")
    detected_entities: list[DetectedEntity] = Field(default_factory=list, alias="detectedEntities")
    status: ToolApprovalStatus


class WebUIUserAttachment(WebUIModel):
    """Per-attachment record returned to the frontend after redaction.

    Both the original and the redacted artifact are echoed back as
    base64-encoded data URLs. The originals normally live only in the
    uploading browser tab's memory, but a page reload would otherwise
    lose the local-vs-remote diff entirely — the vault stores both so
    the diff stays reconstructible across reloads while honoring
    CloakBot's "data never leaves localhost" boundary (the vault is
    local-only).

    ``original_data_url`` and ``redacted_data_url`` are both ``None``
    when the visual pipeline omitted the image (fail-closed); callers
    render a placeholder in that case.
    """

    status: Literal["redacted", "omitted"]
    original_data_url: str | None = Field(default=None, alias="originalDataUrl")
    redacted_data_url: str | None = Field(default=None, alias="redactedDataUrl")
    redaction: VisualPrivacyRedaction | None = None
    reason: str | None = None


class WebUIPrivacyTurn(WebUIModel):
    turn_id: str = Field(alias="turnId")
    intent: Literal["chat", "math"]
    remote_prompt: str = Field(alias="remotePrompt")
    local_computations: list[LocalComputationRecord] = Field(alias="localComputations")
    tool_results: list[WebUIToolResult] = Field(default_factory=list, alias="toolResults")
    tool_approvals: list[WebUIToolApproval] = Field(default_factory=list, alias="toolApprovals")
    user_attachments: list[WebUIUserAttachment] = Field(default_factory=list, alias="userAttachments")


class WebUIPrivacyTimelineEvent(WebUIModel):
    event_type: str = Field(alias="eventType")
    sequence: int
    stage: str
    status: str
    span_id: str = Field(alias="spanId")
    parent_span_id: str | None = Field(default=None, alias="parentSpanId")
    timestamp: datetime
    duration_ms: int | None = Field(default=None, alias="durationMs")
    payload: dict[str, Any]


class WebUIPrivacyTimeline(WebUIModel):
    turn_id: str = Field(alias="turnId")
    trace_id: str = Field(alias="traceId")
    total_duration_ms: int = Field(alias="totalDurationMs")
    stage_durations_ms: dict[str, int] = Field(alias="stageDurationsMs")
    events: list[WebUIPrivacyTimelineEvent]


class WebUIPrivacyPayload(WebUIModel):
    privacy: SessionPrivacySnapshot
    privacy_annotations: list[RestoredTokenAnnotation] = Field(alias="privacyAnnotations")
    privacy_turn: WebUIPrivacyTurn = Field(alias="privacyTurn")
    privacy_timeline: WebUIPrivacyTimeline = Field(alias="privacyTimeline")


class WebUISessionEvent(WebUIModel):
    type: Literal["session"] = "session"
    session_id: str = Field(alias="sessionId")


class WebUIStatusEvent(WebUIModel):
    type: Literal["status"] = "status"
    data: WebUIStatusData


class WebUIPrivacySnapshotEvent(WebUIModel):
    type: Literal["privacy_snapshot"] = "privacy_snapshot"
    data: SessionPrivacySnapshot


class WebUIProgressEvent(WebUIModel):
    type: Literal["progress"] = "progress"
    content: str
    tool_hint: bool = Field(alias="toolHint")


class WebUIAssistantMessageEvent(WebUIModel):
    type: Literal["assistant_message"] = "assistant_message"
    content: str
    privacy: SessionPrivacySnapshot | None = None
    privacy_annotations: list[RestoredTokenAnnotation] | None = Field(default=None, alias="privacyAnnotations")
    privacy_turn: WebUIPrivacyTurn | None = Field(default=None, alias="privacyTurn")
    privacy_timeline: WebUIPrivacyTimeline | None = Field(default=None, alias="privacyTimeline")
    tool_approval: WebUIToolApproval | None = Field(default=None, alias="toolApproval")


class WebUIAssistantDeltaEvent(WebUIModel):
    type: Literal["assistant_delta"] = "assistant_delta"
    content: str


class WebUIAssistantDoneEvent(WebUIModel):
    type: Literal["assistant_done"] = "assistant_done"
    privacy: SessionPrivacySnapshot | None = None
    privacy_annotations: list[RestoredTokenAnnotation] | None = Field(default=None, alias="privacyAnnotations")
    privacy_turn: WebUIPrivacyTurn | None = Field(default=None, alias="privacyTurn")
    privacy_timeline: WebUIPrivacyTimeline | None = Field(default=None, alias="privacyTimeline")
