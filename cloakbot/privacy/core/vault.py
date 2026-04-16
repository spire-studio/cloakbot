"""Session map storage for privacy placeholder vaults."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from loguru import logger

# Canonical placeholder format: <<TAG_N>>
PLACEHOLDER_RE = re.compile(r"<<[A-Z]+(?:_[A-Z]+)*_\d+>>")


@dataclass
class _SessionMap:
    """In-memory view of a session's placeholder mapping table."""

    original_to_placeholder: dict[str, str]  # "Alice"      → "<<PERSON_1>>"
    placeholder_to_original: dict[str, str]  # "<<PERSON_1>>" → "Alice"
    placeholder_to_value: dict[str, Union[int, float, str]] = field(
        default_factory=dict,
    )  # "<<AMOUNT_1>>" → 100.0
    counters: dict[str, int] = field(default_factory=dict)  # "PERSON" → 1

    # -- Placeholder lifecycle management --------------------------------

    def get_or_create_placeholder(
        self, original: str, tag: str
    ) -> tuple[str, bool]:
        """Return ``(placeholder, is_new)``.

        Idempotent — the same *original* text always maps to the same
        placeholder regardless of how many times this method is called.
        """
        if original in self.original_to_placeholder:
            return self.original_to_placeholder[original], False

        self.counters[tag] = self.counters.get(tag, 0) + 1
        placeholder = f"<<{tag}_{self.counters[tag]}>>"
        self.original_to_placeholder[original] = placeholder
        self.placeholder_to_original[placeholder] = original
        return placeholder, True

    def set_computable_value(
        self, placeholder: str, value: int | float | str
    ) -> None:
        """Store the normalised numeric value for a computable placeholder."""
        self.placeholder_to_value[placeholder] = value


_cache: dict[str, _SessionMap] = {}
_TOKEN_RE = re.compile(r"^<<[A-Z]+(?:_[A-Z]+)*_\d+>>$")


def _safe_key(session_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_key)


def _map_path(session_key: str) -> Path:
    maps_dir = Path.home() / ".cloakbot" / "sanitizer_maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    return maps_dir / f"{_safe_key(session_key)}.json"


def _load_map(session_key: str) -> _SessionMap:
    path = _map_path(session_key)
    if path.exists():
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            o2p: dict[str, str] = data.get("original_to_placeholder", {})
            p2o: dict[str, str] = data.get("placeholder_to_original", {})

            # Prune corrupted entries where original → placeholder → placeholder
            o2p = {k: v for k, v in o2p.items() if not PLACEHOLDER_RE.search(k)}
            p2o = {k: v for k, v in p2o.items() if not PLACEHOLDER_RE.search(v)}

            return _SessionMap(
                original_to_placeholder=o2p,
                placeholder_to_original=p2o,
                placeholder_to_value=data.get("placeholder_to_value", {}),
                counters=data.get("counters", {}),
            )
        except Exception:
            logger.warning("sanitizer: corrupt session map at {}; resetting", path)
    return _SessionMap({}, {}, {}, {})


def _save_map(session_key: str, smap: _SessionMap) -> None:
    path = _map_path(session_key)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f"{path.name}.", suffix=".tmp", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(json.dumps({
                "original_to_placeholder": smap.original_to_placeholder,
                "placeholder_to_original": smap.placeholder_to_original,
                "placeholder_to_value": smap.placeholder_to_value,
                "counters": smap.counters,
            }, ensure_ascii=False, indent=2))
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path: tmp_path.unlink(missing_ok=True)
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
