"""Best-effort content-type sniffing for tool payloads.

The detection runs over potentially adversarial content (web pages,
JSON tool returns, file dumps), so the sniffer is intentionally
*conservative*: when in doubt it falls back to ``TEXT`` rather than
applying a fancier chunker that might mis-segment and let PII slip
through structural seams.

Sniffing is cheap (no parsing) — it's only enough signal to pick the
right :class:`Chunker`; the chunker itself does the structural work.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any


class ContentType(str, Enum):
    TEXT = "text"
    JSON = "json"
    HTML = "html"
    MARKDOWN = "markdown"


# Cheap prefix probes. Order matters — JSON before HTML before MD,
# because a Markdown doc can contain ``<...>`` tokens and a JSON doc
# always starts with `{` / `[`.
_HTML_HINTS = ("<!doctype html", "<html", "<head", "<body", "<div", "<span", "<table", "<p>", "<br", "<a ")
_MARKDOWN_HINTS = ("\n# ", "\n## ", "\n```", "\n- ", "\n* ", "\n> ", "\n---", "\n| ")


def sniff_content_type(payload: Any) -> ContentType:
    """Return the most plausible :class:`ContentType` for *payload*.

    Accepts already-parsed structures (``dict`` / ``list``) and strings.
    Bytes are treated as opaque ``TEXT`` — image payloads should go
    through ``process_visual_blocks`` instead, never through this path.
    """
    if isinstance(payload, (dict, list)):
        return ContentType.JSON
    if not isinstance(payload, str):
        return ContentType.TEXT

    head = payload.lstrip()[:512].lower()
    if not head:
        return ContentType.TEXT

    # JSON: parse-validate the first KiB so we don't misclassify
    # JSON-shaped strings that aren't actually JSON.
    if head[0] in "{[":
        candidate = payload.strip()
        if len(candidate) <= 16_384:
            try:
                json.loads(candidate)
                return ContentType.JSON
            except (json.JSONDecodeError, ValueError):
                pass
        else:
            # Cheap heuristic for large payloads: starts with `{"` or
            # `[{`, contains a balanced closer in the first KiB.
            if head.startswith(("{\"", "[{", "{\"")) and ("\":" in head or "\": " in head):
                return ContentType.JSON

    if any(hint in head for hint in _HTML_HINTS):
        return ContentType.HTML

    # Match Markdown only when the leading whitespace-stripped payload
    # itself starts with a Markdown construct, or contains multiple
    # heading-like lines in the head. This avoids matching one stray
    # ``- `` inside otherwise plain text.
    if head.startswith(("# ", "## ", "```", "- ", "* ", "> ")):
        return ContentType.MARKDOWN
    if sum(1 for hint in _MARKDOWN_HINTS if hint in payload[:2048]) >= 2:
        return ContentType.MARKDOWN

    return ContentType.TEXT


__all__ = ["ContentType", "sniff_content_type"]
