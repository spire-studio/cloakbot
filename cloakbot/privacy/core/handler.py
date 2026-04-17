"""Privacy token application helpers."""

from __future__ import annotations

import re

from cloakbot.privacy.core.vault import PLACEHOLDER_RE, _SessionMap
from cloakbot.privacy.core.types import REGISTRY, DetectionResult, ComputableEntity

_IS_PLACEHOLDER_RE = re.compile(r"^<<[A-Z]+(?:_[A-Z]+)*_\d+>>$")


def _find_protected_spans(text: str) -> list[tuple[int, int]]:
    """Return sorted ``(start, end)`` spans for every existing ``<<TOKEN>>``."""
    return [(m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(text)]


def _overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """True if ``[start, end)`` overlaps with any protected span."""
    return any(s < end and start < e for s, e in spans)


def _find_safe_positions(
    text: str,
    needle: str,
    protected: list[tuple[int, int]],
) -> list[int]:
    """Return start positions of *needle* that don't overlap protected spans."""
    positions: list[int] = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            break
        if not _overlaps_any(idx, idx + len(needle), protected):
            positions.append(idx)
        start = idx + 1
    return positions


def apply_tokens(detection: DetectionResult, smap: _SessionMap) -> tuple[str, bool]:
    """
    Replace sensitive entities with placeholders using span-aware replacement.

    Existing ``<<...>>`` placeholders in the text are treated as protected
    zones and will never be corrupted by replacements.
    """
    sensitive = detection.sensitive_entities
    if not sensitive:
        return detection.original_prompt, False

    ordered = sorted(sensitive, key=lambda e: len(e.text), reverse=True)
    text = detection.original_prompt
    tag_map = REGISTRY.tag_map
    modified = False

    for entity in ordered:
        # Skip entities that are themselves placeholders
        if _IS_PLACEHOLDER_RE.fullmatch(entity.text):
            continue
        if "<<" in entity.text and ">>" in entity.text:
            continue

        # Find protected zones (existing placeholders)
        protected = _find_protected_spans(text)

        # Find safe (non-overlapping) positions for this entity
        positions = _find_safe_positions(text, entity.text, protected)
        if not positions:
            continue

        # Get or create placeholder via vault
        tag = tag_map.get(entity.entity_type, "ENTITY")
        placeholder, _is_new = smap.get_or_create_placeholder(entity.text, tag)

        # Store computable value if applicable
        if isinstance(entity, ComputableEntity):
            smap.set_computable_value(placeholder, entity.value)

        # Replace from right to left to preserve earlier positions
        for pos in reversed(positions):
            text = text[:pos] + placeholder + text[pos + len(entity.text):]
        modified = True

    return text, modified
