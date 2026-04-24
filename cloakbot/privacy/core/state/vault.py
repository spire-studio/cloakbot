"""Session map storage for privacy placeholder vaults."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from cloakbot.config.paths import get_privacy_vault_dir

# Canonical placeholder format: <<TAG_N>>
PLACEHOLDER_RE = re.compile(r"<<[A-Z]+(?:_[A-Z]+)*_\d+>>")
_TOKEN_RE = re.compile(r"^<<([A-Z]+(?:_[A-Z]+)*)_(\d+)>>$")


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


class _SessionMap(BaseModel):
    """In-memory view of a session's placeholder registry."""

    original_to_placeholder: dict[str, str] = Field(default_factory=dict)
    normalized_to_placeholder: dict[str, str] = Field(default_factory=dict)
    placeholder_to_original: dict[str, str] = Field(default_factory=dict)
    placeholder_to_entity: dict[str, VaultEntity] = Field(default_factory=dict)
    placeholder_to_value: dict[str, int | float | str] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)

    def normalize_text(self, text: str) -> str:
        """Collapse benign formatting differences for alias matching."""
        collapsed = " ".join(text.strip().split()).lower()
        if not collapsed:
            return ""
        cleaned = re.sub(r"[^\w\s]", "", collapsed)
        return cleaned or collapsed

    def _placeholder_tag(self, placeholder: str) -> str | None:
        match = _TOKEN_RE.fullmatch(placeholder)
        return match.group(1) if match else None

    def _entity_type_from_tag(self, tag: str) -> str:
        return tag.lower()

    def _ensure_entity(self, placeholder: str) -> VaultEntity:
        entity = self.placeholder_to_entity.get(placeholder)
        if entity is not None:
            return entity

        canonical = self.placeholder_to_original.get(placeholder, placeholder)
        tag = self._placeholder_tag(placeholder) or "ENTITY"
        entity = VaultEntity(
            placeholder=placeholder,
            entity_type=self._entity_type_from_tag(tag),
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
        """Reconstruct secondary indexes from the entity registry and legacy fields."""
        merged_original_to_placeholder = dict(self.original_to_placeholder)
        merged_placeholder_to_original = dict(self.placeholder_to_original)
        merged_placeholder_to_value = dict(self.placeholder_to_value)

        for placeholder, canonical in merged_placeholder_to_original.items():
            if placeholder not in self.placeholder_to_entity:
                tag = self._placeholder_tag(placeholder) or "ENTITY"
                self.placeholder_to_entity[placeholder] = VaultEntity(
                    placeholder=placeholder,
                    entity_type=self._entity_type_from_tag(tag),
                    canonical=canonical,
                    aliases=[canonical],
                    normalized_aliases=[],
                    value=merged_placeholder_to_value.get(placeholder),
                )

        for original, placeholder in merged_original_to_placeholder.items():
            entity = self._ensure_entity(placeholder)
            if original not in entity.aliases:
                entity.aliases.append(original)

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
            entity_type=self._entity_type_from_tag(tag),
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
                protected = [(m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(text_out)]
                if any(s < end and idx < e for s, e in protected):
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


_cache: dict[str, _SessionMap] = {}
_workspace: Path | None = None


def set_vault_workspace(workspace: str | Path) -> None:
    global _workspace
    next_workspace = Path(workspace).expanduser()
    if _workspace != next_workspace:
        _cache.clear()
    _workspace = next_workspace


def _safe_key(session_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_key)


def _map_path(session_key: str) -> Path:
    maps_dir = get_privacy_vault_dir(_workspace) / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    return maps_dir / f"{_safe_key(session_key)}.json"


def _prune_legacy_indexes(
    original_to_placeholder: dict[str, str],
    placeholder_to_original: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    filtered_original_to_placeholder = {
        original: placeholder
        for original, placeholder in original_to_placeholder.items()
        if not PLACEHOLDER_RE.search(original)
    }
    filtered_placeholder_to_original = {
        placeholder: original
        for placeholder, original in placeholder_to_original.items()
        if not PLACEHOLDER_RE.search(original)
    }
    return filtered_original_to_placeholder, filtered_placeholder_to_original


def _load_map(session_key: str) -> _SessionMap:
    path = _map_path(session_key)
    if path.exists():
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            original_to_placeholder, placeholder_to_original = _prune_legacy_indexes(
                data.get("original_to_placeholder", {}),
                data.get("placeholder_to_original", {}),
            )

            raw_entities = data.get("placeholder_to_entity", {})
            placeholder_to_entity = {
                placeholder: VaultEntity.model_validate(payload)
                for placeholder, payload in raw_entities.items()
            }

            smap = _SessionMap(
                original_to_placeholder=original_to_placeholder,
                normalized_to_placeholder=data.get("normalized_to_placeholder", {}),
                placeholder_to_original=placeholder_to_original,
                placeholder_to_entity=placeholder_to_entity,
                placeholder_to_value=data.get("placeholder_to_value", {}),
                counters=data.get("counters", {}),
            )
            smap.rebuild_indexes()
            return smap
        except Exception:
            logger.warning("sanitizer: corrupt session map at {}; resetting", path)
    return _SessionMap()


def _save_map(session_key: str, smap: _SessionMap) -> None:
    path = _map_path(session_key)
    tmp_path: Path | None = None
    smap.rebuild_indexes()
    payload = smap.model_dump(mode="json")
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(json.dumps(payload, ensure_ascii=False, indent=2))
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def get_map(session_key: str) -> _SessionMap:
    if session_key not in _cache:
        _cache[session_key] = _load_map(session_key)
    return _cache[session_key]


def save_map(session_key: str, smap: _SessionMap) -> None:
    _save_map(session_key, smap)
    _cache[session_key] = smap


def clear_cache(session_key: str) -> None:
    _cache.pop(session_key, None)
