from __future__ import annotations

from pathlib import Path

import cloakbot.privacy.core.state.vault as vault
from cloakbot.privacy.core.state.vault import (
    _safe_key,
    delete_session_vault,
    get_map,
    get_privacy_vault_dir,
    set_vault_workspace,
)


def _seed(tmp_path: Path, key: str) -> tuple[Path, Path, Path]:
    """Write a placeholder map, a per-turn privacy log, and a tool-artifacts dir."""
    set_vault_workspace(tmp_path)
    vault._cache.clear()
    safe = _safe_key(key)
    root = get_privacy_vault_dir(tmp_path)
    map_path = root / "maps" / f"{safe}.json"
    turns_path = root / "turns" / f"{safe}.jsonl"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    turns_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text("{}", encoding="utf-8")
    turns_path.write_text("{}\n", encoding="utf-8")
    artifacts_root = root / "artifacts" / safe
    blob = artifacts_root / "turn-1" / "call-1" / "blob.bin"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"secret")
    return map_path, turns_path, artifacts_root


def test_delete_session_vault_cascade_removes_all_artifacts(tmp_path: Path) -> None:
    key = "websocket:abc-123"
    map_path, turns_path, artifacts_dir = _seed(tmp_path, key)
    # Warm the in-memory cache so we also prove eviction.
    get_map(key)
    assert vault._cache

    assert delete_session_vault(key) is True
    assert not map_path.exists()
    assert not turns_path.exists()
    assert not artifacts_dir.exists()
    assert not vault._cache


def test_delete_session_vault_is_idempotent(tmp_path: Path) -> None:
    set_vault_workspace(tmp_path)
    vault._cache.clear()
    # Nothing on disk -> returns False without raising.
    assert delete_session_vault("websocket:never-existed") is False


def test_delete_session_vault_only_targets_the_named_session(tmp_path: Path) -> None:
    keep_map, keep_turns, keep_artifacts = _seed(tmp_path, "websocket:keep-me")
    drop_map, drop_turns, drop_artifacts = _seed(tmp_path, "websocket:drop-me")

    assert delete_session_vault("websocket:drop-me") is True
    assert not drop_map.exists()
    assert not drop_turns.exists()
    assert not drop_artifacts.exists()
    # The other session's vault is untouched.
    assert keep_map.exists()
    assert keep_turns.exists()
    assert keep_artifacts.exists()
