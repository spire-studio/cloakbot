from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cloakbot.privacy.protocol.contracts import EventRecord, EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.metrics import MetricsSnapshot, build_metrics_snapshot
from cloakbot.privacy.protocol.replay import SessionTraceIndex


@dataclass
class InMemoryEventSink:
    events: list[EventRecord] = field(default_factory=list)

    def emit(self, event: EventRecord) -> None:
        self.events.append(event)

    def clear(self) -> None:
        self.events.clear()
        _TRACE_INDEX.clear()
        _SEQUENCE_BY_TRACE.clear()
        _START_EVENT_BY_TRACE_AND_SPAN.clear()


_EVENT_SINK = InMemoryEventSink()
_TRACE_INDEX = SessionTraceIndex()
_SEQUENCE_BY_TRACE: dict[str, int] = {}
_START_EVENT_BY_TRACE_AND_SPAN: dict[tuple[str, str], EventRecord] = {}


def get_event_sink() -> InMemoryEventSink:
    return _EVENT_SINK


def get_session_trace_index() -> SessionTraceIndex:
    return _TRACE_INDEX


def get_metrics_snapshot() -> MetricsSnapshot:
    return build_metrics_snapshot(_EVENT_SINK.events)


def emit_event(
    *,
    event_type: EventType,
    trace_id: str,
    span_id: str,
    session_id: str,
    turn_id: str,
    stage: PrivacyStage,
    status: ProtocolStatus,
    payload: dict[str, Any],
    parent_span_id: str | None = None,
) -> None:
    sequence = _SEQUENCE_BY_TRACE.get(trace_id, 0) + 1
    _SEQUENCE_BY_TRACE[trace_id] = sequence
    timestamp = datetime.now(timezone.utc)
    duration_ms = None

    if parent_span_id is not None:
        start_event = _START_EVENT_BY_TRACE_AND_SPAN.get((trace_id, parent_span_id))
        if start_event is not None:
            duration_ms = max(int((timestamp - start_event.timestamp).total_seconds() * 1000), 0)

    event = EventRecord(
        event_type=event_type,
        event_version="v1",
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        sequence=sequence,
        session_id=session_id,
        turn_id=turn_id,
        stage=stage,
        status=status,
        timestamp=timestamp,
        duration_ms=duration_ms,
        payload=payload,
    )
    _EVENT_SINK.emit(event)
    _TRACE_INDEX.append(event)

    if status is ProtocolStatus.STARTED:
        _START_EVENT_BY_TRACE_AND_SPAN[(trace_id, span_id)] = event
