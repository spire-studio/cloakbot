"""Event-protocol schema for the privacy turn timeline.

These types are the wire/record contract for the observability event stream:
`emit_event` mints an :class:`EventRecord`, the sink stores it, and the replay /
metrics layers read it back. Nothing here is aspirational — every type has a
live producer or consumer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

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


__all__ = ["EventRecord", "EventType", "PrivacyStage", "ProtocolStatus"]
