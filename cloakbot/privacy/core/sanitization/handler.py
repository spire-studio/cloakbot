"""Privacy token application helpers."""

from __future__ import annotations

from cloakbot.privacy.core.placeholders import find_unprotected_positions, is_placeholder
from cloakbot.privacy.core.sanitization.alias_resolver import resolve_existing_placeholder
from cloakbot.privacy.core.state.vault import _SessionMap
from cloakbot.privacy.core.types import REGISTRY, ComputableEntity, DetectionResult, GeneralEntity


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

        # Get or create placeholder via vault.
        tag = tag_map.get(entity.entity_type, "ENTITY")

        # Detector-emitted cross-turn dedupe decision (Plan C). When the local
        # model has already judged whether this surface refers to a known
        # entity, it overrides the substring resolver — which only looks at
        # lexical overlap and cannot distinguish "another person who shares a
        # surname" from "the same person partially mentioned". A None / unknown
        # hint falls back to the resolver. Only GeneralEntity carries a hint.
        hint = entity.dedupe_hint if isinstance(entity, GeneralEntity) else None

        placeholder: str | None = None
        if hint == "new":
            # Skip alias matching entirely. The Vault may still return an
            # existing placeholder via `get_or_create_placeholder` if the
            # surface text is already an EXACT alias of a registered entity,
            # but that is the safe lexical-equality case (e.g. the same
            # value repeated verbatim across turns), not the structural
            # over-merging we are trying to avoid here.
            placeholder, _is_new = smap.get_or_create_placeholder(
                entity.text,
                tag,
                turn_id=turn_id,
            )
        elif hint and is_placeholder(hint) and hint in smap.placeholder_to_entity:
            # Detector says this surface is the SAME as an existing
            # placeholder. Honor it verbatim and register the surface as
            # an additional alias of that placeholder.
            placeholder = hint
            smap.register_alias(placeholder, entity.text, turn_id=turn_id)
        else:
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
