"""Plain-text chunker with paragraph/line awareness + overlap."""

from __future__ import annotations

from typing import Any

from cloakbot.privacy.core.detection.chunking.base import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    Chunk,
)


class PlainTextChunker:
    """Greedy chunker that respects paragraph and line boundaries.

    Strategy:
      1. Split the payload into paragraphs (separated by blank lines).
      2. Greedily pack paragraphs into a chunk up to ``max_chars``.
      3. When a single paragraph exceeds the budget, fall back to
         line-level splitting and finally to hard character cuts.
      4. Each chunk after the first is prepended with the trailing
         ``overlap_chars`` of the previous chunk so an entity that
         straddles the seam ("Laurie\\nLuo") is still seen as one span
         by the detector.

    The overlap is purely additive — duplicate detection results are
    deduped at the orchestrator level by vault lookup, so the overlap
    never produces double placeholders.
    """

    name = "plaintext"
    version = "1"

    def chunk(
        self,
        payload: Any,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> list[Chunk]:
        text = payload if isinstance(payload, str) else str(payload or "")
        if not text:
            return []
        if len(text) <= max_chars:
            return [Chunk(index=0, text=text, char_span=(0, len(text)))]

        segments = _segment_with_offsets(text)
        chunks: list[Chunk] = []
        buf: list[str] = []
        buf_start: int | None = None
        buf_end = 0

        def flush() -> None:
            nonlocal buf, buf_start, buf_end
            if not buf or buf_start is None:
                return
            body = "".join(buf)
            if chunks and overlap_chars > 0:
                prev_tail = chunks[-1].text[-overlap_chars:]
                body = prev_tail + body
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=body,
                    char_span=(buf_start, buf_end),
                    provenance={"chunker": "plaintext"},
                )
            )
            buf = []
            buf_start = None

        for seg_text, seg_start, seg_end in segments:
            if buf_start is None:
                buf_start = seg_start
            # Soft fit: append while under budget.
            if sum(len(s) for s in buf) + len(seg_text) <= max_chars or not buf:
                buf.append(seg_text)
                buf_end = seg_end
                # Single segment overflowed budget on its own — hard-cut.
                if not buf or sum(len(s) for s in buf) > max_chars:
                    flush()
                continue
            flush()
            buf.append(seg_text)
            buf_start = seg_start
            buf_end = seg_end

        flush()
        # Hard-cut any chunk that is still oversized (a single paragraph
        # bigger than the budget). Rare but possible for log dumps.
        return list(_enforce_hard_cut(chunks, max_chars=max_chars, overlap_chars=overlap_chars))


def _segment_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Split *text* on blank lines, then on single newlines for big paragraphs."""
    out: list[tuple[str, int, int]] = []
    pos = 0
    length = len(text)
    while pos < length:
        # Find blank-line boundary.
        boundary = text.find("\n\n", pos)
        if boundary == -1:
            boundary = length
        else:
            boundary += 2  # include the blank line in the previous segment
        out.append((text[pos:boundary], pos, boundary))
        pos = boundary
    return out


def _enforce_hard_cut(
    chunks: list[Chunk],
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[Chunk]:
    if all(len(c.text) <= max_chars for c in chunks):
        return chunks
    cut: list[Chunk] = []
    for chunk in chunks:
        if len(chunk.text) <= max_chars:
            cut.append(_reindex(chunk, len(cut)))
            continue
        body = chunk.text
        start = 0
        while start < len(body):
            end = min(len(body), start + max_chars)
            cut.append(
                Chunk(
                    index=len(cut),
                    text=body[start:end],
                    char_span=chunk.char_span,
                    provenance={**chunk.provenance, "hard_cut": True},
                )
            )
            start = max(start + max_chars - overlap_chars, end)
    return cut


def _reindex(chunk: Chunk, new_index: int) -> Chunk:
    if chunk.index == new_index:
        return chunk
    return Chunk(
        index=new_index,
        text=chunk.text,
        char_span=chunk.char_span,
        provenance=chunk.provenance,
    )


__all__ = ["PlainTextChunker"]
