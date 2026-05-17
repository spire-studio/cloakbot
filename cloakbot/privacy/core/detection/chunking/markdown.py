"""Markdown chunker.

Markdown PII tends to cluster inside sections (a "## Contact" block
holds emails / phones) and inside code fences (config dumps that
accidentally include API keys). The chunker tries hard to keep these
units intact: a chunk boundary is preferred at a heading or a fence
boundary, never inside a fenced block.
"""

from __future__ import annotations

import re
from typing import Any

from cloakbot.privacy.core.detection.chunking.base import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    Chunk,
)
from cloakbot.privacy.core.detection.chunking.text import PlainTextChunker

_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)
_FENCE_RE = re.compile(r"^```", re.MULTILINE)


class MarkdownChunker:
    name = "markdown"
    version = "1"

    def __init__(self) -> None:
        self._inner = PlainTextChunker()

    def chunk(
        self,
        payload: Any,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> list[Chunk]:
        if not isinstance(payload, str):
            payload = str(payload or "")
        if not payload:
            return []

        sections = _split_at_headings(payload)
        # First pass: group sections greedily into chunks honouring
        # fence integrity. Then hand any oversized section to the
        # plain-text chunker for line-level split.
        intermediate: list[Chunk] = []
        buf: list[str] = []

        def flush() -> None:
            if not buf:
                return
            text = "\n".join(buf)
            intermediate.append(
                Chunk(
                    index=len(intermediate),
                    text=text,
                    char_span=None,
                    provenance={"chunker": "markdown"},
                )
            )
            buf.clear()

        for section in sections:
            section_len = len(section)
            current_len = sum(len(s) + 1 for s in buf)
            if buf and current_len + section_len > max_chars and not _has_open_fence(buf):
                flush()
            buf.append(section)
        flush()

        # Second pass: blow up oversized chunks via the text chunker so
        # we never exceed the budget.
        out: list[Chunk] = []
        for chunk in intermediate:
            if len(chunk.text) <= max_chars:
                out.append(_reindex(chunk, len(out)))
                continue
            sub = self._inner.chunk(
                chunk.text,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
            for s in sub:
                out.append(
                    Chunk(
                        index=len(out),
                        text=s.text,
                        char_span=None,
                        provenance={
                            "chunker": "markdown",
                            "subchunker": "plaintext",
                        },
                    )
                )
        return out


def _split_at_headings(text: str) -> list[str]:
    """Split markdown into heading-anchored sections.

    Each returned section starts at a heading (or at the document
    start) and ends just before the next heading, so the heading text
    stays attached to its body.
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [text]

    sections: list[str] = []
    if matches[0].start() > 0:
        head = text[: matches[0].start()].rstrip()
        if head:
            sections.append(head)
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end].rstrip()
        if section:
            sections.append(section)
    return sections


def _has_open_fence(buf: list[str]) -> bool:
    """``True`` if the buffered sections contain an unclosed code fence.

    Used as a guard so we don't break a chunk in the middle of a
    fenced block — the detector benefits from seeing the whole block
    (paths, env vars, etc.) at once.
    """
    fence_count = 0
    for s in buf:
        fence_count += len(_FENCE_RE.findall(s))
    return fence_count % 2 == 1


def _reindex(chunk: Chunk, new_index: int) -> Chunk:
    if chunk.index == new_index:
        return chunk
    return Chunk(
        index=new_index,
        text=chunk.text,
        char_span=chunk.char_span,
        provenance=chunk.provenance,
    )


__all__ = ["MarkdownChunker"]
