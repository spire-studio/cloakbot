"""In-memory placeholder registry: the data model for one session's vault.

This is the lowest layer of the vault. It holds the placeholder ↔ surface-form
mappings, alias normalisation, and computable-value bookkeeping for a single
session, with no disk or scope-routing concerns (those live in ``vault_store``
and ``scope``). The public facade is :mod:`cloakbot.privacy.core.state.vault`.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from cloakbot.privacy.core.placeholders import (
    PLACEHOLDER_RE,
    overlaps_any,
    placeholder_tag,
    protected_spans,
)


class VaultEntity(BaseModel):
    """One stable placeholder identity plus its known surface forms."""

    placeholder: str
    entity_type: str
    canonical: str
    aliases: list[str] = Field(default_factory=list)
    normalized_aliases: list[str] = Field(default_factory=list)
    value: int | float | str | None = None
    created_turn: str | None = None
    last_seen_turn: str | None = None


class VaultComputation(BaseModel):
    """A persisted local calculation that can be reused in later turns."""

    placeholder: str
    expression: str
    resolved_expression: str
    source_placeholders: list[str] = Field(default_factory=list)
    value: float
    formatted_value: str
    created_turn: str | None = None
    last_seen_turn: str | None = None


class _SessionMap(BaseModel):
    """In-memory view of a session's placeholder registry."""

    original_to_placeholder: dict[str, str] = Field(default_factory=dict)
    normalized_to_placeholder: dict[str, str] = Field(default_factory=dict)
    placeholder_to_original: dict[str, str] = Field(default_factory=dict)
    placeholder_to_entity: dict[str, VaultEntity] = Field(default_factory=dict)
    placeholder_to_value: dict[str, int | float | str] = Field(default_factory=dict)
    placeholder_to_computation: dict[str, VaultComputation] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)

    def normalize_text(self, text: str) -> str:
        """Collapse benign formatting differences for alias matching.

        Steps:
          1. NFKC normalisation (full-width → half-width, ligatures
             unfolded), so ``"ＡＢＣ"`` aliases to ``"abc"``.
          2. Strip combining marks (NFD then drop ``Mn``), so
             ``"café"`` aliases to ``"cafe"``.
          3. Whitespace collapse + lowercase.
          4. Punctuation removal — but if the result would be empty we
             fall back to the punctuation-preserving form so tokens
             like email handles still resolve.
        """
        if not text:
            return ""
        normalised = unicodedata.normalize("NFKC", text)
        decomposed = unicodedata.normalize("NFD", normalised)
        no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
        collapsed = " ".join(no_marks.strip().split()).lower()
        if not collapsed:
            return ""
        cleaned = re.sub(r"[^\w\s]", "", collapsed)
        return cleaned or collapsed

    def _ensure_entity(self, placeholder: str) -> VaultEntity:
        entity = self.placeholder_to_entity.get(placeholder)
        if entity is not None:
            return entity

        canonical = self.placeholder_to_original.get(placeholder, placeholder)
        tag = placeholder_tag(placeholder) or "ENTITY"
        entity = VaultEntity(
            placeholder=placeholder,
            entity_type=tag.lower(),
            canonical=canonical,
            aliases=[canonical] if canonical and canonical != placeholder else [],
            normalized_aliases=[],
            value=self.placeholder_to_value.get(placeholder),
        )
        self.placeholder_to_entity[placeholder] = entity
        self._sync_entity_indexes(placeholder)
        return entity

    def _sync_entity_indexes(self, placeholder: str) -> None:
        entity = self.placeholder_to_entity.get(placeholder)
        if entity is None:
            return

        if entity.canonical:
            self.placeholder_to_original[placeholder] = entity.canonical

        aliases: list[str] = []
        seen_aliases: set[str] = set()
        for alias in [entity.canonical, *entity.aliases]:
            if not alias or alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            aliases.append(alias)
        entity.aliases = aliases

        normalized_aliases: list[str] = []
        seen_normalized: set[str] = set()
        for alias in entity.aliases:
            self.original_to_placeholder[alias] = placeholder
            normalized = self.normalize_text(alias)
            if normalized:
                self.normalized_to_placeholder[normalized] = placeholder
            if normalized and normalized not in seen_normalized:
                seen_normalized.add(normalized)
                normalized_aliases.append(normalized)
        entity.normalized_aliases = normalized_aliases

        if entity.value is not None:
            self.placeholder_to_value[placeholder] = entity.value

    def rebuild_indexes(self) -> None:
        """Reconstruct secondary indexes from the entity registry and stored fields."""
        merged_original_to_placeholder = dict(self.original_to_placeholder)
        merged_placeholder_to_original = dict(self.placeholder_to_original)
        merged_placeholder_to_value = dict(self.placeholder_to_value)

        for placeholder, canonical in merged_placeholder_to_original.items():
            if placeholder not in self.placeholder_to_entity:
                tag = placeholder_tag(placeholder) or "ENTITY"
                self.placeholder_to_entity[placeholder] = VaultEntity(
                    placeholder=placeholder,
                    entity_type=tag.lower(),
                    canonical=canonical,
                    aliases=[canonical],
                    normalized_aliases=[],
                    value=merged_placeholder_to_value.get(placeholder),
                )

        for original, placeholder in merged_original_to_placeholder.items():
            entity = self._ensure_entity(placeholder)
            if original not in entity.aliases:
                entity.aliases.append(original)

        for placeholder, computation in self.placeholder_to_computation.items():
            if placeholder not in self.placeholder_to_entity:
                self.placeholder_to_entity[placeholder] = VaultEntity(
                    placeholder=placeholder,
                    entity_type="local_computation",
                    canonical=computation.formatted_value,
                    aliases=[computation.formatted_value],
                    value=computation.value,
                    created_turn=computation.created_turn,
                    last_seen_turn=computation.last_seen_turn,
                )

        self.original_to_placeholder = {}
        self.normalized_to_placeholder = {}
        self.placeholder_to_original = {}
        self.placeholder_to_value = {}

        for placeholder in list(self.placeholder_to_entity):
            self._sync_entity_indexes(placeholder)

    def lookup_placeholder(self, text: str) -> str | None:
        if text in self.original_to_placeholder:
            return self.original_to_placeholder[text]
        normalized = self.normalize_text(text)
        if normalized:
            return self.normalized_to_placeholder.get(normalized)
        return None

    def register_alias(
        self,
        placeholder: str,
        alias: str,
        *,
        turn_id: str | None = None,
    ) -> None:
        entity = self._ensure_entity(placeholder)
        if alias and alias not in entity.aliases:
            entity.aliases.append(alias)
        if turn_id is not None:
            if entity.created_turn is None:
                entity.created_turn = turn_id
            entity.last_seen_turn = turn_id
        self._sync_entity_indexes(placeholder)

    def get_or_create_placeholder(
        self,
        original: str,
        tag: str,
        *,
        turn_id: str | None = None,
    ) -> tuple[str, bool]:
        """Return ``(placeholder, is_new)`` for one surface form."""
        existing = self.lookup_placeholder(original)
        if existing is not None:
            self.register_alias(existing, original, turn_id=turn_id)
            return existing, False

        self.counters[tag] = self.counters.get(tag, 0) + 1
        placeholder = f"<<{tag}_{self.counters[tag]}>>"
        entity = VaultEntity(
            placeholder=placeholder,
            entity_type=tag.lower(),
            canonical=original,
            aliases=[original],
            normalized_aliases=[],
            created_turn=turn_id,
            last_seen_turn=turn_id,
        )
        self.placeholder_to_entity[placeholder] = entity
        self._sync_entity_indexes(placeholder)
        return placeholder, True

    def set_computable_value(self, placeholder: str, value: int | float | str) -> None:
        """Store the normalised numeric value for a computable placeholder."""
        entity = self._ensure_entity(placeholder)
        entity.value = value
        self.placeholder_to_value[placeholder] = value

    def find_computation(self, expression: str) -> VaultComputation | None:
        """Return a prior local calculation for the same normalized expression."""
        for computation in self.placeholder_to_computation.values():
            if computation.expression == expression:
                return computation
        return None

    def get_computation(self, placeholder: str) -> VaultComputation | None:
        return self.placeholder_to_computation.get(placeholder)

    def get_or_create_computation(
        self,
        *,
        expression: str,
        resolved_expression: str,
        source_placeholders: list[str],
        value: float,
        formatted_value: str,
        turn_id: str | None = None,
    ) -> tuple[VaultComputation, bool]:
        existing = self.find_computation(expression)
        if existing is not None:
            existing.last_seen_turn = turn_id or existing.last_seen_turn
            return existing, False

        tag = "CALC"
        self.counters[tag] = self.counters.get(tag, 0) + 1
        placeholder = f"<<{tag}_{self.counters[tag]}>>"
        computation = VaultComputation(
            placeholder=placeholder,
            expression=expression,
            resolved_expression=resolved_expression,
            source_placeholders=source_placeholders,
            value=value,
            formatted_value=formatted_value,
            created_turn=turn_id,
            last_seen_turn=turn_id,
        )
        self.placeholder_to_computation[placeholder] = computation

        entity = VaultEntity(
            placeholder=placeholder,
            entity_type="local_computation",
            canonical=formatted_value,
            aliases=[formatted_value],
            value=value,
            created_turn=turn_id,
            last_seen_turn=turn_id,
        )
        self.placeholder_to_entity[placeholder] = entity
        self._sync_entity_indexes(placeholder)
        return computation, True

    def replace_known_originals(self, text: str) -> tuple[str, bool]:
        """Swap already known surface forms to stable placeholders before detection."""
        if not self.original_to_placeholder:
            return text, False

        text_out = text
        modified = False

        for original, placeholder in sorted(
            self.original_to_placeholder.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if not original or PLACEHOLDER_RE.search(original):
                continue

            start = 0
            while True:
                idx = text_out.find(original, start)
                if idx == -1:
                    break
                end = idx + len(original)
                if overlaps_any(idx, end, protected_spans(text_out)):
                    start = idx + 1
                    continue
                text_out = text_out[:idx] + placeholder + text_out[end:]
                modified = True
                start = idx + len(placeholder)

        return text_out, modified

    def display_value(self, placeholder: str) -> str:
        entity = self.placeholder_to_entity.get(placeholder)
        if entity is not None and entity.canonical:
            return entity.canonical
        return self.placeholder_to_original.get(placeholder, placeholder)


__all__ = ["VaultComputation", "VaultEntity", "_SessionMap"]
