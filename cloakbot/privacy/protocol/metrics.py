from __future__ import annotations

from dataclasses import dataclass

from cloakbot.privacy.protocol.contracts import EventRecord


@dataclass
class MetricsSnapshot:
    total_events: int
    stage_counts: dict[str, int]
    status_counts: dict[str, int]
    duration_ms: int


def build_metrics_snapshot(events: list[EventRecord]) -> MetricsSnapshot:
    if not events:
        return MetricsSnapshot(total_events=0, stage_counts={}, status_counts={}, duration_ms=0)

    stage_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for event in events:
        stage_key = event.stage.value
        status_key = event.status.value
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

    duration = int((events[-1].timestamp - events[0].timestamp).total_seconds() * 1000)
    return MetricsSnapshot(
        total_events=len(events),
        stage_counts=stage_counts,
        status_counts=status_counts,
        duration_ms=max(duration, 0),
    )
