from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cloakbot.privacy.core.math.math_executor import LocalComputationRecord
from cloakbot.privacy.core.sanitization.restorer import RestoredTokenAnnotation
from cloakbot.privacy.transparency.report import SessionPrivacySnapshot

WEBUI_PRIVACY_METADATA_KEY = "webuiPrivacy"


class WebUIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WebUIUserMessage(WebUIModel):
    content: str


class WebUIStatusData(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    ready: bool
    frontend_built: bool = Field(alias="frontendBuilt")


class WebUIPrivacyTurn(WebUIModel):
    turn_id: str = Field(alias="turnId")
    intent: Literal["chat", "math", "doc"]
    remote_prompt: str = Field(alias="remotePrompt")
    local_computations: list[LocalComputationRecord] = Field(alias="localComputations")


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


class WebUIAssistantDeltaEvent(WebUIModel):
    type: Literal["assistant_delta"] = "assistant_delta"
    content: str


class WebUIAssistantDoneEvent(WebUIModel):
    type: Literal["assistant_done"] = "assistant_done"
    privacy: SessionPrivacySnapshot | None = None
    privacy_annotations: list[RestoredTokenAnnotation] | None = Field(default=None, alias="privacyAnnotations")
    privacy_turn: WebUIPrivacyTurn | None = Field(default=None, alias="privacyTurn")
    privacy_timeline: WebUIPrivacyTimeline | None = Field(default=None, alias="privacyTimeline")
