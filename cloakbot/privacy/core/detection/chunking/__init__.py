"""Content-type-aware chunkers for tool output privacy detection.

The chunkers slice a tool result into bounded pieces that the local PII
detection model can actually swallow (typical local-vLLM context budget
is a few thousand tokens). Each chunker knows the structural rules of
its content type so that:

- entities don't get split across chunk boundaries
  (handled by an overlap window or by respecting structural seams);
- the parent payload can be reassembled or reasoned about as a whole
  after detection.

Public surface:

- :class:`Chunk`       — one slice with span metadata
- :class:`Chunker`     — strategy interface
- :func:`sniff_content_type` — best-effort detection
- :func:`get_chunker`  — registry lookup with safe text fallback
"""

from __future__ import annotations

from cloakbot.privacy.core.detection.chunking.base import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    Chunk,
    Chunker,
)
from cloakbot.privacy.core.detection.chunking.html import HtmlChunker
from cloakbot.privacy.core.detection.chunking.json_chunker import JsonChunker
from cloakbot.privacy.core.detection.chunking.markdown import MarkdownChunker
from cloakbot.privacy.core.detection.chunking.sniffer import (
    ContentType,
    sniff_content_type,
)
from cloakbot.privacy.core.detection.chunking.text import PlainTextChunker

_REGISTRY: dict[ContentType, Chunker] = {
    ContentType.TEXT: PlainTextChunker(),
    ContentType.JSON: JsonChunker(),
    ContentType.HTML: HtmlChunker(),
    ContentType.MARKDOWN: MarkdownChunker(),
}


def get_chunker(content_type: ContentType) -> Chunker:
    """Return the chunker registered for *content_type*.

    Falls back to :class:`PlainTextChunker` for unknown types so the
    detector never silently skips a payload.
    """
    return _REGISTRY.get(content_type, _REGISTRY[ContentType.TEXT])


__all__ = [
    "DEFAULT_MAX_CHARS",
    "DEFAULT_OVERLAP_CHARS",
    "Chunk",
    "Chunker",
    "ContentType",
    "HtmlChunker",
    "JsonChunker",
    "MarkdownChunker",
    "PlainTextChunker",
    "get_chunker",
    "sniff_content_type",
]
