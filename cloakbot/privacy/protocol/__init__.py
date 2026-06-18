"""Privacy turn observability protocol: event schema, sink, metrics, replay."""

from cloakbot.privacy.protocol.contracts import (
    EventRecord,
    EventType,
    PrivacyStage,
    ProtocolStatus,
)
from cloakbot.privacy.protocol.metrics import MetricsSnapshot, build_metrics_snapshot
from cloakbot.privacy.protocol.observability import (
    InMemoryEventSink,
    emit_event,
    get_event_sink,
    get_metrics_snapshot,
    get_session_trace_index,
)
from cloakbot.privacy.protocol.replay import (
    SessionTraceIndex,
    TurnTimeline,
    build_turn_timeline,
)

__all__ = [
    "EventRecord",
    "EventType",
    "InMemoryEventSink",
    "MetricsSnapshot",
    "PrivacyStage",
    "ProtocolStatus",
    "SessionTraceIndex",
    "TurnTimeline",
    "build_metrics_snapshot",
    "build_turn_timeline",
    "emit_event",
    "get_event_sink",
    "get_metrics_snapshot",
    "get_session_trace_index",
]
