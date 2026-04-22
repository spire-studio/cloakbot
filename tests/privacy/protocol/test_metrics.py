from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cloakbot.privacy.protocol.contracts import EventRecord, EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.metrics import build_metrics_snapshot


def _event(event_type: EventType, stage: PrivacyStage, status: ProtocolStatus, dt: datetime) -> EventRecord:
    return EventRecord(
        event_type=event_type,
        event_version="v1",
        trace_id="trace-1",
        span_id="span-1",
        session_id="session-1",
        turn_id="turn-1",
        stage=stage,
        status=status,
        timestamp=dt,
        payload={},
    )


def test_build_metrics_snapshot_aggregates_by_stage_and_status() -> None:
    start = datetime.now(timezone.utc)
    events = [
        _event(EventType.TURN_SANITIZE_STARTED, PrivacyStage.RAW, ProtocolStatus.STARTED, start),
        _event(EventType.TURN_SANITIZE_SUCCEEDED, PrivacyStage.SANITIZED, ProtocolStatus.SUCCEEDED, start + timedelta(milliseconds=12)),
        _event(EventType.TURN_DISPATCH_STARTED, PrivacyStage.SANITIZED, ProtocolStatus.STARTED, start + timedelta(milliseconds=12)),
        _event(EventType.TURN_DISPATCH_COMPLETED, PrivacyStage.SANITIZED, ProtocolStatus.SUCCEEDED, start + timedelta(milliseconds=30)),
    ]

    snapshot = build_metrics_snapshot(events)

    assert snapshot.total_events == 4
    assert snapshot.status_counts["succeeded"] == 2
    assert snapshot.stage_counts["sanitized"] == 3
    assert snapshot.duration_ms >= 0
