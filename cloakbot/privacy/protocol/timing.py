"""Shared timing helper for protocol event durations."""

from __future__ import annotations

from datetime import datetime


def elapsed_ms(start: datetime, end: datetime) -> int:
    """Whole milliseconds between two timestamps, clamped at zero."""
    return max(int((end - start).total_seconds() * 1000), 0)


__all__ = ["elapsed_ms"]
