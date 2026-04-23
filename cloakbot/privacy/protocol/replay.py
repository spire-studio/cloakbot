from __future__ import annotations

from dataclasses import dataclass, field

from cloakbot.privacy.protocol.contracts import EventRecord


@dataclass
class TurnTimeline:
    session_id: str
    turn_id: str
    trace_id: str
    events: list[EventRecord]
    total_duration_ms: int
    stage_durations_ms: dict[str, int]


@dataclass
class SessionTraceIndex:
    _events_by_session: dict[str, list[EventRecord]] = field(default_factory=dict)
    _events_by_trace: dict[str, list[EventRecord]] = field(default_factory=dict)

    def append(self, event: EventRecord) -> None:
        self._events_by_session.setdefault(event.session_id, []).append(event)
        self._events_by_trace.setdefault(event.trace_id, []).append(event)

    def replay(self, session_id: str) -> list[EventRecord]:
        return self.replay_session(session_id)

    def replay_session(self, session_id: str) -> list[EventRecord]:
        return sorted(self._events_by_session.get(session_id, []), key=_event_sort_key)

    def replay_trace(self, trace_id: str) -> list[EventRecord]:
        return sorted(self._events_by_trace.get(trace_id, []), key=_event_sort_key)

    def replay_turn(self, session_id: str, turn_id: str) -> list[EventRecord]:
        return [
            event
            for event in self.replay_session(session_id)
            if event.turn_id == turn_id
        ]

    def clear(self) -> None:
        self._events_by_session.clear()
        self._events_by_trace.clear()


def build_turn_timeline(session_id: str, turn_id: str, *, index: SessionTraceIndex | None = None) -> TurnTimeline:
    if index is None:
        from cloakbot.privacy.protocol.observability import get_session_trace_index

        trace_index = get_session_trace_index()
    else:
        trace_index = index
    events = trace_index.replay_turn(session_id, turn_id)
    if not events:
        return TurnTimeline(
            session_id=session_id,
            turn_id=turn_id,
            trace_id="",
            events=[],
            total_duration_ms=0,
            stage_durations_ms={},
        )

    total_duration_ms = max(int((events[-1].timestamp - events[0].timestamp).total_seconds() * 1000), 0)
    stage_durations_ms: dict[str, int] = {}
    for event in events:
        if event.duration_ms is None:
            continue
        stage_key = event.event_type.value.split(".")[-2]
        stage_durations_ms[stage_key] = event.duration_ms

    return TurnTimeline(
        session_id=session_id,
        turn_id=turn_id,
        trace_id=events[0].trace_id,
        events=events,
        total_duration_ms=total_duration_ms,
        stage_durations_ms=stage_durations_ms,
    )


def _event_sort_key(event: EventRecord) -> tuple[int, str]:
    return event.sequence, event.timestamp.isoformat()
