from __future__ import annotations

from cloakbot.privacy.protocol.contracts import EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.observability import (
    emit_event,
    get_event_sink,
    get_metrics_snapshot,
    get_session_trace_index,
)
from cloakbot.privacy.protocol.replay import build_turn_timeline


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
    replay = get_session_trace_index().replay_session("session-1")

    assert snapshot.total_events >= 2
    assert snapshot.status_counts["started"] >= 1
    assert snapshot.status_counts["succeeded"] >= 1
    assert len(replay) >= 2


def test_observability_builds_turn_timeline_with_stage_durations() -> None:
    sink = get_event_sink()
    sink.clear()

    emit_event(
        event_type=EventType.TURN_RECEIVED,
        trace_id="trace-2",
        span_id="received-1",
        session_id="session-2",
        turn_id="turn-2",
        stage=PrivacyStage.RAW,
        status=ProtocolStatus.STARTED,
        payload={"intent": "chat"},
    )
    emit_event(
        event_type=EventType.TURN_SANITIZE_STARTED,
        trace_id="trace-2",
        span_id="sanitize-1",
        session_id="session-2",
        turn_id="turn-2",
        stage=PrivacyStage.RAW,
        status=ProtocolStatus.STARTED,
        payload={},
    )
    emit_event(
        event_type=EventType.TURN_SANITIZE_SUCCEEDED,
        trace_id="trace-2",
        span_id="sanitize-2",
        parent_span_id="sanitize-1",
        session_id="session-2",
        turn_id="turn-2",
        stage=PrivacyStage.SANITIZED,
        status=ProtocolStatus.SUCCEEDED,
        payload={},
    )
    emit_event(
        event_type=EventType.TURN_COMPLETED,
        trace_id="trace-2",
        span_id="completed-1",
        session_id="session-2",
        turn_id="turn-2",
        stage=PrivacyStage.POSTPROCESSED,
        status=ProtocolStatus.SUCCEEDED,
        payload={},
    )

    timeline = build_turn_timeline("session-2", "turn-2")

    assert timeline.trace_id == "trace-2"
    assert [event.sequence for event in timeline.events] == [1, 2, 3, 4]
    assert timeline.events[2].duration_ms is not None
    assert timeline.stage_durations_ms["sanitize"] == timeline.events[2].duration_ms
    assert timeline.total_duration_ms >= timeline.stage_durations_ms["sanitize"]
