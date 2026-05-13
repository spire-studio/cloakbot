"""Tests for the v1 alias resolver enhancements.

Covers two recently-added behaviours:

  * ORG tag now participates in substring/normalisation coalescing,
    so ``"Anthropic"`` and ``"Anthropic, Inc."`` resolve to the same
    placeholder.
  * ``_SessionMap.normalize_text`` now NFKC-normalises and strips
    combining marks, so full-width / accented duplicates of the same
    name don't allocate fresh placeholders.
"""

from __future__ import annotations

from cloakbot.privacy.core.sanitization.alias_resolver import (
    resolve_existing_placeholder,
)
from cloakbot.privacy.core.state.vault import _SessionMap


def test_org_substring_alias_resolves_to_existing_placeholder() -> None:
    smap = _SessionMap()
    placeholder, _ = smap.get_or_create_placeholder(
        "Anthropic, Inc.", "ORG", turn_id="turn-1"
    )

    # The short surface ("Anthropic") should coalesce onto the longer
    # canonical, mirroring the PERSON behaviour.
    reused = resolve_existing_placeholder("Anthropic", "ORG", smap)
    assert reused == placeholder


def test_org_substring_alias_does_not_match_unrelated_token() -> None:
    """Two-character substrings must not greedily merge unrelated orgs."""
    smap = _SessionMap()
    smap.get_or_create_placeholder("Anthropic", "ORG", turn_id="turn-1")

    # "An" appears inside "Anthropic" but is far too short to be
    # treated as the same entity. Resolver must allocate fresh.
    assert resolve_existing_placeholder("An", "ORG", smap) is None


def test_normalize_text_collapses_fullwidth_to_halfwidth() -> None:
    """Full-width Latin chars (common in CJK locales) coalesce onto ASCII."""
    smap = _SessionMap()
    assert smap.normalize_text("ＡＢＣ") == smap.normalize_text("ABC")


def test_normalize_text_strips_diacritics() -> None:
    """``café`` and ``cafe`` should normalise to the same key."""
    smap = _SessionMap()
    assert smap.normalize_text("café") == smap.normalize_text("cafe")


def test_normalize_text_handles_empty_input() -> None:
    smap = _SessionMap()
    assert smap.normalize_text("") == ""
    assert smap.normalize_text("   \n\t  ") == ""


def test_diacritic_variant_resolves_onto_existing_placeholder() -> None:
    smap = _SessionMap()
    placeholder, _ = smap.get_or_create_placeholder(
        "Café Anthropic", "ORG", turn_id="turn-1"
    )

    reused = resolve_existing_placeholder("Cafe Anthropic", "ORG", smap)
    assert reused == placeholder
