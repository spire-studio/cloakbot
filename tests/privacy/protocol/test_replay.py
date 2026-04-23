from __future__ import annotations

from datetime import datetime, timezone

from cloakbot.privacy.protocol.contracts import EventRecord, EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.replay import SessionTraceIndex


def test_session_trace_index_stores_and_replays_by_session() -> None:
    index = SessionTraceIndex()
    event = EventRecord(
        event_type=EventType.TURN_RECEIVED,
        event_version="v1",
        trace_id="trace-1",
        span_id="span-1",
        session_id="session-1",
        turn_id="turn-1",
        stage=PrivacyStage.RAW,
        status=ProtocolStatus.STARTED,
        timestamp=datetime.now(timezone.utc),
        payload={"intent": "chat"},
    )

    index.append(event)
    replay = index.replay("session-1")

    assert len(replay) == 1
    assert replay[0].event_type == EventType.TURN_RECEIVED
