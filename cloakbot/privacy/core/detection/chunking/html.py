"""HTML chunker.

PII in HTML lives in three places:
  * visible body text
  * ``mailto:`` / ``tel:`` / ``data-*`` attributes referenced from links
  * ``<meta>`` head fields (author, og:email, …)

The chunker normalises an HTML payload into a single newline-separated
text stream covering all three, then delegates the windowing to
:class:`PlainTextChunker`. The goal is *recall*: better to leak a tiny
HTML tag into the detector than to miss an ``href="mailto:…"`` because
the chunker walked past it.

We deliberately avoid pulling in BeautifulSoup; the tag-strip below is
not safe HTML rendering, just enough to recover the textual content
that a privacy detector should see.
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

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RUN_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL,
)
_HREF_RE = re.compile(
    r"""\b(?:href|src|content|action|cite|data-[\w-]+)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_META_RE = re.compile(
    r"""<meta\b[^>]*?(?:name|property|http-equiv)\s*=\s*["']([^"']+)["'][^>]*?content\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)


class HtmlChunker:
    name = "html"
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

        normalized = _normalize_html(payload)
        if not normalized:
            return []
        chunks = self._inner.chunk(
            normalized, max_chars=max_chars, overlap_chars=overlap_chars,
        )
        return [
            Chunk(
                index=c.index,
                text=c.text,
                char_span=None,
                provenance={**c.provenance, "chunker": "html"},
            )
            for c in chunks
        ]


def _normalize_html(html: str) -> str:
    """Best-effort HTML → text extraction with attribute mining.

    The output is ordered as: ``<meta>`` payloads first (they often carry
    author/email), then attribute URLs (``mailto:`` etc.), then the
    visible body text. Each segment is separated by blank lines so the
    plain-text chunker can split on paragraph boundaries.
    """
    parts: list[str] = []

    metas = _META_RE.findall(html)
    if metas:
        parts.append(
            "\n".join(f"meta[{name}]: {content}" for name, content in metas),
        )

    refs: list[str] = []
    for url in _HREF_RE.findall(html):
        url = url.strip()
        if not url:
            continue
        if url.startswith(("mailto:", "tel:")) or url.lower().startswith(("http://", "https://", "ftp://", "ftps://", "file://")):
            refs.append(url)
        elif url.startswith(("/", "./", "../")):
            # Relative path — may itself encode usernames / IDs.
            refs.append(url)
    if refs:
        parts.append("\n".join(refs))

    body = _SCRIPT_STYLE_RE.sub(" ", html)
    body = _TAG_RE.sub(" ", body)
    body = _WHITESPACE_RUN_RE.sub(" ", body).strip()
    if body:
        parts.append(body)

    return "\n\n".join(parts).strip()


__all__ = ["HtmlChunker"]
