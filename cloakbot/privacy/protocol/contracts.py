from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ProtocolStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PrivacyStage(str, Enum):
    RAW = "raw"
    SANITIZED = "sanitized"
    POSTPROCESSED = "postprocessed"


class EventType(str, Enum):
    TURN_RECEIVED = "turn.received"
    TURN_INTENT_CLASSIFIED = "turn.intent.classified"
    TURN_SANITIZE_STARTED = "turn.sanitize.started"
    TURN_SANITIZE_SUCCEEDED = "turn.sanitize.succeeded"
    TURN_SANITIZE_FAILED = "turn.sanitize.failed"
    TURN_DISPATCH_STARTED = "turn.agent.dispatch.started"
    TURN_DISPATCH_COMPLETED = "turn.agent.dispatch.completed"
    TURN_DISPATCH_FAILED = "turn.agent.dispatch.failed"
    TURN_RESTORE_STARTED = "turn.restore.started"
    TURN_RESTORE_COMPLETED = "turn.restore.completed"
    TURN_RESTORE_FAILED = "turn.restore.failed"
    TURN_COMPLETED = "turn.completed"


class ContractMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    span_id: str
    session_id: str
    turn_id: str
    idempotency_key: str
    timestamp: datetime
    status: ProtocolStatus
    error_code: str


class TurnContextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["chat", "math", "doc"]
    channel: Literal["cli", "gateway", "webui", "api"]
    privacy_stage: PrivacyStage


class TurnContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: ContractMeta
    context: TurnContextPayload
    payload: dict[str, Any]


class AgentTaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: Literal["intent_analysis", "math_exec", "doc_parse", "tool_chain"]
    mode: Literal["sync", "async"]
    priority: Literal["p0", "p1", "p2"]
    deadline_ms: int


class AgentTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: ContractMeta
    task: AgentTaskSpec
    input: dict[str, Any]


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    timeout_ms: int


class ToolPrivacySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sanitize_before: bool
    sanitize_after: bool


class ToolInvocationContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: ContractMeta
    tool: ToolSpec
    input: dict[str, Any]
    privacy: ToolPrivacySpec


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    event_version: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    sequence: int = 0
    session_id: str
    turn_id: str
    stage: PrivacyStage
    status: ProtocolStatus
    timestamp: datetime
    duration_ms: int | None = None
    payload: dict[str, Any]
