"""On-disk storage primitives for the privacy vault.

Pure serialization / filesystem layer: workspace-scoped paths, atomic map
persistence, and tool-artifact bytes. It knows the :class:`_SessionMap` data
model but nothing about scopes or caches — scope routing and live-map access
live in :mod:`cloakbot.privacy.core.state.scope`, and the public facade is
:mod:`cloakbot.privacy.core.state.vault`.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from cloakbot.config.paths import get_workspace_path
from cloakbot.privacy.core.placeholders import PLACEHOLDER_RE
from cloakbot.privacy.core.state.registry import VaultComputation, VaultEntity, _SessionMap

_workspace: Path | None = None


def get_privacy_vault_dir(workspace: str | Path | None = None) -> Path:
    """Workspace-scoped privacy vault directory.

    Privacy-owned to avoid patching upstream ``config/paths.py`` (keeps it
    mergeable on rebase). Mirrors the pre-rebase semantics.
    """
    base = Path(workspace).expanduser() if workspace is not None else get_workspace_path()
    path = base / "privacy_vault"
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def current_workspace() -> Path | None:
    """Return the workspace the vault is currently bound to (``None`` = default)."""
    return _workspace


def set_workspace(workspace: str | Path) -> bool:
    """Bind the vault to *workspace*. Returns ``True`` if it changed."""
    global _workspace
    next_workspace = Path(workspace).expanduser()
    changed = _workspace != next_workspace
    _workspace = next_workspace
    return changed


def _safe_key(session_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_key)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def _map_path(session_key: str) -> Path:
    maps_dir = get_privacy_vault_dir(_workspace) / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    return maps_dir / f"{_safe_key(session_key)}.json"


def _artifacts_dir(session_key: str, turn_id: str, tool_call_id: str) -> Path:
    root = get_privacy_vault_dir(_workspace) / "artifacts"
    path = root / _safe_key(session_key) / _safe_key(turn_id) / _safe_key(tool_call_id)
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


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
            raw_computations = data.get("placeholder_to_computation", {})
            placeholder_to_computation = {
                placeholder: VaultComputation.model_validate(payload)
                for placeholder, payload in raw_computations.items()
            }

            smap = _SessionMap(
                original_to_placeholder=original_to_placeholder,
                normalized_to_placeholder=data.get("normalized_to_placeholder", {}),
                placeholder_to_original=placeholder_to_original,
                placeholder_to_entity=placeholder_to_entity,
                placeholder_to_value=data.get("placeholder_to_value", {}),
                placeholder_to_computation=placeholder_to_computation,
                counters=data.get("counters", {}),
            )
            smap.rebuild_indexes()
            return smap
        except (OSError, ValueError):
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


def _write_artifact_atomic(path: Path, data: bytes) -> Path:
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)
        os.replace(tmp_path, path)
        path.chmod(0o600)
        return path
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def save_artifact_bytes(
    session_key: str,
    turn_id: str,
    tool_call_id: str,
    filename: str,
    data: bytes,
) -> Path:
    path = _artifacts_dir(session_key, turn_id, tool_call_id) / _safe_filename(filename)
    return _write_artifact_atomic(path, data)


def save_artifact_text(
    session_key: str,
    turn_id: str,
    tool_call_id: str,
    filename: str,
    text: str,
) -> Path:
    return save_artifact_bytes(
        session_key,
        turn_id,
        tool_call_id,
        filename,
        text.encode("utf-8"),
    )


__all__ = [
    "current_workspace",
    "get_privacy_vault_dir",
    "save_artifact_bytes",
    "save_artifact_text",
    "set_workspace",
]
