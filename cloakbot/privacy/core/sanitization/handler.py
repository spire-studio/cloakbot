"""Privacy token application helpers."""

from __future__ import annotations

from cloakbot.privacy.core.placeholders import find_unprotected_positions, is_placeholder
from cloakbot.privacy.core.sanitization.alias_resolver import resolve_existing_placeholder
from cloakbot.privacy.core.state.vault import _SessionMap
from cloakbot.privacy.core.types import REGISTRY, ComputableEntity, DetectionResult


def apply_tokens(
    detection: DetectionResult,
    smap: _SessionMap,
    *,
    turn_id: str | None = None,
) -> tuple[str, bool]:
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
        if is_placeholder(entity.text):
            continue
        if "<<" in entity.text and ">>" in entity.text:
            continue

        # Find safe (non-overlapping) positions for this entity, avoiding any
        # existing placeholder spans already in the text.
        positions = find_unprotected_positions(text, entity.text)
        if not positions:
            continue

        # Get or create placeholder via vault. Cross-turn aliasing is handled by
        # the substring resolver: it reuses an existing placeholder when the
        # surface is a known alias (e.g. "Laurie" → "Laurie Luo"), and returns
        # None on ambiguity so a fresh placeholder is allocated instead.
        tag = tag_map.get(entity.entity_type, "ENTITY")

        placeholder = resolve_existing_placeholder(entity.text, tag, smap)
        if placeholder is not None:
            smap.register_alias(placeholder, entity.text, turn_id=turn_id)
        else:
            placeholder, _is_new = smap.get_or_create_placeholder(
                entity.text,
                tag,
                turn_id=turn_id,
            )

        # Store computable value if applicable
        if isinstance(entity, ComputableEntity):
            smap.set_computable_value(placeholder, entity.value)

        # Replace from right to left to preserve earlier positions
        for pos in reversed(positions):
            text = text[:pos] + placeholder + text[pos + len(entity.text):]
        modified = True

    return text, modified
