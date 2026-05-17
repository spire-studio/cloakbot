"""Shared chunker primitives.

A :class:`Chunk` carries enough provenance for the orchestrator to map a
detected entity back to its position in the original payload, which is
what makes cross-chunk vault coalescing meaningful (the vault keys on
*text* and the chunk metadata lets us prove "this is the same string,
just observed twice").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# Default budget knobs. Tuned so a typical local-vLLM call (~2k token
# output budget, ~8k input window) has comfortable headroom. Each chunk
# may still be smaller — chunkers prefer to break at structural seams.
DEFAULT_MAX_CHARS = 6000
DEFAULT_OVERLAP_CHARS = 300


@dataclass(frozen=True)
class Chunk:
    """One slice of a tool payload, ready for PII detection."""

    index: int
    text: str
    # Byte/char span in the *original* serialized payload. ``None`` for
    # structural chunks (e.g. one JSON array element) where a contiguous
    # span does not exist.
    char_span: tuple[int, int] | None = None
    # Free-form provenance — e.g. ``{"json_path": "$.users[3].email"}``.
    # The orchestrator passes this back into telemetry / restoration but
    # does not interpret it.
    provenance: dict[str, Any] = field(default_factory=dict)


class Chunker(Protocol):
    """Strategy for splitting a payload into PII-detectable chunks.

    Implementations should be cheap and synchronous; the heavy lifting
    (LLM-based PII detection) runs after chunking.

    The contract:
      * ``chunk(payload)`` never returns more chunks than necessary —
        a payload smaller than the budget yields a single chunk.
      * Order is preserved: chunks come out in the order they appear in
        the payload, so the orchestrator can reconstruct.
      * Each chunk's ``text`` must be a plain string (no bytes / dicts);
        structural chunkers serialize their slice before yielding.
    """

    name: str
    version: str

    def chunk(
        self,
        payload: Any,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> list[Chunk]: ...


__all__ = ["Chunk", "Chunker", "DEFAULT_MAX_CHARS", "DEFAULT_OVERLAP_CHARS"]
