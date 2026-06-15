from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from cloakbot.privacy.protocol.contracts import EventRecord
from cloakbot.privacy.protocol.timing import elapsed_ms


@dataclass
class MetricsSnapshot:
    total_events: int
    stage_counts: dict[str, int]
    status_counts: dict[str, int]
    duration_ms: int


def build_metrics_snapshot(events: list[EventRecord]) -> MetricsSnapshot:
    if not events:
        return MetricsSnapshot(total_events=0, stage_counts={}, status_counts={}, duration_ms=0)

    stage_counts = Counter(event.stage.value for event in events)
    status_counts = Counter(event.status.value for event in events)
    return MetricsSnapshot(
        total_events=len(events),
        stage_counts=dict(stage_counts),
        status_counts=dict(status_counts),
        duration_ms=elapsed_ms(events[0].timestamp, events[-1].timestamp),
    )
