from __future__ import annotations

from cloakbot.privacy.core.state.vault import _SessionMap

# Tags where substring/normalization-style alias coalescing is allowed.
# Keeping the set small avoids accidentally merging two distinct
# entities (e.g. ``invoice_number`` "INV-001" must NOT merge into
# "INV-0011"); names and organisations are the well-trodden cases.
_SUBSTRING_ALIAS_TAGS = {"PERSON", "ORG"}


def resolve_existing_placeholder(text: str, tag: str, smap: _SessionMap) -> str | None:
    """Resolve a likely cross-turn alias onto an existing placeholder.

    Strategy (v1):
      1. Exact (post-normalize) lookup against existing vault aliases.
      2. For ``PERSON`` / ``ORG`` tags only: substring-aware coalescing
         so ``"Laurie"`` and ``"Laurie Luo"`` share one placeholder,
         and ``"Anthropic, Inc."`` collapses to ``"Anthropic"``.
      3. Ambiguity is fatal — if two existing placeholders both look
         like a match, return ``None`` and the caller allocates a fresh
         token. Over-merging silently corrupts restoration; we err on the
         side of producing extra placeholders.
    """
    existing = smap.lookup_placeholder(text)
    if existing is not None:
        return existing

    normalized = smap.normalize_text(text)
    if not normalized:
        return None

    candidates: list[str] = []
    for placeholder, entity in smap.placeholder_to_entity.items():
        if not placeholder.startswith(f"<<{tag}_"):
            continue
        if normalized in entity.normalized_aliases:
            candidates.append(placeholder)
            continue

        if tag in _SUBSTRING_ALIAS_TAGS and _substring_alias_match(
            normalized, entity.normalized_aliases,
        ):
            candidates.append(placeholder)

    if len(candidates) == 1:
        return candidates[0]
    return None


def _substring_alias_match(normalized: str, alias_list: list[str]) -> bool:
    """Return ``True`` when *normalized* and any known alias share a stem.

    Used for tags whose canonical surface is multi-token (names,
    organisation suffixes): we match either as a substring of an
    existing alias or as a superset, but only when the shorter side is
    non-trivial (≥2 chars) and a clean token boundary exists. This
    keeps "Li" out of "Lisa" while still catching "Laurie" inside
    "Laurie Luo".
    """
    if not normalized or not alias_list:
        return False
    tokens = normalized.split()
    for alias in alias_list:
        if not alias:
            continue
        alias_tokens = alias.split()
        # Single-token query: must appear as a whole token in the alias.
        if len(tokens) == 1:
            if len(tokens[0]) >= 2 and tokens[0] in alias_tokens:
                return True
            continue
        # Multi-token query: prefix/suffix of an existing alias, or
        # the existing alias is a prefix/suffix of the query.
        if (
            normalized == alias
            or normalized.endswith(alias)
            or alias.endswith(normalized)
            or normalized.startswith(alias)
            or alias.startswith(normalized)
        ):
            return True
    return False
