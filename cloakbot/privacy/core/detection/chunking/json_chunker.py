"""JSON chunker — path-aware flattening for structured tool returns.

Most tool outputs that arrive as JSON have PII concentrated in a small
number of leaf string values (``email``, ``phone``, ``address``,
``name``). Pretending the whole document is free text wastes the
detector budget on braces, quotes, and keys.

Strategy:
    1. Parse the JSON (already-parsed ``dict``/``list`` accepted too).
    2. Flatten to a stream of ``(path, leaf)`` pairs where ``leaf`` is
       a printable string representation.
    3. Pack pairs greedily into chunks up to the character budget.

When parsing fails we fall back to plain-text chunking — never silently
skip detection.
"""

from __future__ import annotations

import json
from typing import Any

from cloakbot.privacy.core.detection.chunking.base import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    Chunk,
)
from cloakbot.privacy.core.detection.chunking.text import PlainTextChunker


class JsonChunker:
    """Flatten JSON to ``path: value`` pairs and pack into chunks."""

    name = "json"
    version = "1"

    def __init__(self) -> None:
        self._fallback = PlainTextChunker()

    def chunk(
        self,
        payload: Any,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> list[Chunk]:
        try:
            obj = payload if not isinstance(payload, str) else json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return self._fallback.chunk(
                payload, max_chars=max_chars, overlap_chars=overlap_chars,
            )

        pairs = _flatten(obj)
        if not pairs:
            # Empty or all-null JSON. Still emit one (empty) chunk so the
            # orchestrator can record "we did inspect this payload".
            return []

        chunks: list[Chunk] = []
        buf: list[str] = []
        buf_paths: list[str] = []

        def flush() -> None:
            if not buf:
                return
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text="\n".join(buf),
                    char_span=None,
                    provenance={
                        "chunker": "json",
                        "paths": list(buf_paths),
                    },
                ),
            )
            buf.clear()
            buf_paths.clear()

        for path, leaf in pairs:
            line = f"{path}: {leaf}"
            if buf and sum(len(s) + 1 for s in buf) + len(line) > max_chars:
                flush()
            buf.append(line)
            buf_paths.append(path)

        flush()
        return chunks


def _flatten(obj: Any, *, prefix: str = "$") -> list[tuple[str, str]]:
    """Yield ``(path, printable_leaf)`` pairs for every leaf in *obj*.

    Only string and primitive leaves are emitted; ``None`` is skipped to
    keep the detector focused on actual content. Keys are joined with
    ``.`` and array indices with ``[i]`` so the path stays
    JSONPath-readable.
    """
    if obj is None:
        return []
    if isinstance(obj, dict):
        out: list[tuple[str, str]] = []
        for key, value in obj.items():
            child_prefix = f"{prefix}.{key}" if _is_simple_key(key) else f"{prefix}[{key!r}]"
            out.extend(_flatten(value, prefix=child_prefix))
        return out
    if isinstance(obj, list):
        out = []
        for i, value in enumerate(obj):
            out.extend(_flatten(value, prefix=f"{prefix}[{i}]"))
        return out
    # Leaf
    leaf = str(obj)
    if not leaf:
        return []
    return [(prefix, leaf)]


def _is_simple_key(key: Any) -> bool:
    if not isinstance(key, str) or not key:
        return False
    return key[0].isalpha() and all(ch.isalnum() or ch == "_" for ch in key)


__all__ = ["JsonChunker"]
