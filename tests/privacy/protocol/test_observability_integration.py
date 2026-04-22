from __future__ import annotations

from cloakbot.privacy.protocol.contracts import EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.observability import (
    emit_event,
    get_event_sink,
    get_metrics_snapshot,
    get_session_trace_index,
)


def test_observability_populates_metrics_and_replay_indexes() -> None:
    sink = get_event_sink()
    sink.clear()

    emit_event(
        event_type=EventType.TURN_RECEIVED,
        trace_id="trace-1",
        span_id="span-1",
        session_id="session-1",
        turn_id="turn-1",
        stage=PrivacyStage.RAW,
        status=ProtocolStatus.STARTED,
        payload={"intent": "chat"},
    )
    emit_event(
        event_type=EventType.TURN_COMPLETED,
        trace_id="trace-1",
        span_id="span-2",
        session_id="session-1",
        turn_id="turn-1",
        stage=PrivacyStage.POSTPROCESSED,
        status=ProtocolStatus.SUCCEEDED,
        payload={},
    )

    snapshot = get_metrics_snapshot()
    replay = get_session_trace_index().replay("session-1")

    assert snapshot.total_events >= 2
    assert snapshot.status_counts["started"] >= 1
    assert snapshot.status_counts["succeeded"] >= 1
    assert len(replay) >= 2
