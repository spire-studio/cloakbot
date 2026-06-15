"""Single source of truth for the ``<<TAG_N>>`` placeholder grammar.

The placeholder token is the privacy trust boundary: the sanitizer mints
``<<PERSON_1>>``-style tokens, the remote model only ever sees tokens, and the
restorer maps them back locally. Every module that matches, extracts, or filters
these tokens imports its pattern from here so the grammar can never drift between
the mint path and an egress path (a divergence could silently stop stripping a
token before it crosses the wire).

A token is ``<<`` + TAG + ``_`` + index + ``>>`` where TAG is one or more
uppercase ``A-Z`` segments joined by ``_`` (e.g. ``PERSON``, ``LOCAL_PATH``) and
index is a decimal integer.
"""

from __future__ import annotations

import re

# Unanchored search form, no capture. Use for ``.search`` / ``.finditer`` / ``.sub``;
# ``.fullmatch`` against it is an exact "is this string exactly one token?" check.
PLACEHOLDER_RE = re.compile(r"<<[A-Z]+(?:_[A-Z]+)*_\d+>>")

# Anchored, captures (tag, index) separately — for parsing a single token.
TOKEN_RE = re.compile(r"^<<([A-Z]+(?:_[A-Z]+)*)_(\d+)>>$")

# Unanchored, captures the tag only — for scanning tags embedded in larger text.
PLACEHOLDER_TAG_RE = re.compile(r"<<([A-Z]+(?:_[A-Z]+)*)_\d+>>")

# Loose matcher for the local detector's self-token filter. Brackets are optional
# and the tag head requires >=2 letters, so a bare model echo like ``PERSON_1``
# (no brackets) is still recognised as our own token and dropped from detection,
# not just the fully-bracketed ``<<PERSON_1>>``.
INTERNAL_TOKEN_RE = re.compile(r"(?:<<)?[A-Z]{2,}(?:_[A-Z]+)*_\d+(?:>>)?")


def is_placeholder(text: str) -> bool:
    """True iff *text* is exactly one placeholder token."""
    return PLACEHOLDER_RE.fullmatch(text) is not None


def placeholder_tag(token: str) -> str | None:
    """Return the TAG of a single placeholder token (e.g. ``PERSON``), or ``None``."""
    match = TOKEN_RE.match(token)
    return match.group(1) if match else None


def placeholder_inner(token: str) -> str | None:
    """Return the bracketless body of a token (e.g. ``FINANCE_1``), or ``None``.

    This is the form the math layer uses as a local variable name.
    """
    match = TOKEN_RE.match(token)
    return f"{match.group(1)}_{match.group(2)}" if match else None


def entity_type_from_placeholder(token: str) -> str | None:
    """Return the entity type (lowercased tag) for a placeholder token, or ``None``."""
    tag = placeholder_tag(token)
    return tag.lower() if tag is not None else None


def protected_spans(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` spans for every existing ``<<TOKEN>>`` in *text*.

    These are the zones a replacement must never overwrite — corrupting a minted
    placeholder would break restoration and could re-expose a raw value.
    """
    return [(m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(text)]


def overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """True iff ``[start, end)`` overlaps any span in *spans*."""
    return any(s < end and start < e for s, e in spans)


def find_unprotected_positions(text: str, needle: str) -> list[int]:
    """Start indices of *needle* in *text* that don't overlap an existing token."""
    protected = protected_spans(text)
    positions: list[int] = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            break
        if not overlaps_any(idx, idx + len(needle), protected):
            positions.append(idx)
        start = idx + 1
    return positions


__all__ = [
    "INTERNAL_TOKEN_RE",
    "PLACEHOLDER_RE",
    "PLACEHOLDER_TAG_RE",
    "TOKEN_RE",
    "entity_type_from_placeholder",
    "find_unprotected_positions",
    "is_placeholder",
    "overlaps_any",
    "placeholder_inner",
    "placeholder_tag",
    "protected_spans",
]
