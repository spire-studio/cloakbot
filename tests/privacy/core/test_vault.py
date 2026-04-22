from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import cloakbot.privacy.core.state.vault as vault
from cloakbot.privacy.core.state.vault import _SessionMap


@pytest.fixture()
def isolated_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vault._cache.clear()

    def fake_map_path(session_key: str) -> Path:
        return tmp_path / f"{session_key.replace(':', '_')}.json"

    monkeypatch.setattr(vault, "_map_path", fake_map_path)
    yield
    vault._cache.clear()


def test_get_map_returns_empty_session_map_for_new_session_key(isolated_vault: None) -> None:
    smap = vault.get_map("new:session")

    assert smap == _SessionMap()


def test_save_map_persists_and_get_map_retrieves_it_correctly(isolated_vault: None) -> None:
    session_key = "persist:session"
    smap = _SessionMap()
    placeholder, is_new = smap.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="turn-1")
    assert is_new is True
    smap.register_alias(placeholder, "Alice", turn_id="turn-2")

    vault.save_map(session_key, smap)
    vault.clear_cache(session_key)
    loaded = vault.get_map(session_key)

    assert loaded.original_to_placeholder["Alice Chen"] == "<<PERSON_1>>"
    assert loaded.original_to_placeholder["Alice"] == "<<PERSON_1>>"
    assert loaded.placeholder_to_entity["<<PERSON_1>>"].canonical == "Alice Chen"
    assert loaded.placeholder_to_entity["<<PERSON_1>>"].aliases == ["Alice Chen", "Alice"]


def test_atomic_write_keeps_original_file_intact_on_mid_write_crash(
    isolated_vault: None,
    tmp_path: Path,
) -> None:
    session_key = "atomic:session"
    path = tmp_path / "atomic_session.json"
    original = {
        "original_to_placeholder": {"Alice": "<<PERSON_1>>"},
        "placeholder_to_original": {"<<PERSON_1>>": "Alice"},
        "counters": {"PERSON": 1},
    }
    path.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file = tmp_path / "atomic_session.json.crash.tmp"

    class ExplodingTempFile:
        def __init__(self, name: Path) -> None:
            self.name = str(name)

        def __enter__(self) -> "ExplodingTempFile":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def write(self, data: str) -> int:
            Path(self.name).write_text(data[:20], encoding="utf-8")
            raise RuntimeError("simulated crash")

    with patch.object(vault.tempfile, "NamedTemporaryFile", return_value=ExplodingTempFile(tmp_file)):
        with pytest.raises(RuntimeError, match="simulated crash"):
            vault._save_map(
                session_key,
                _SessionMap(
                    original_to_placeholder={"Bob": "<<PERSON_2>>"},
                    placeholder_to_original={"<<PERSON_2>>": "Bob"},
                    counters={"PERSON": 2},
                ),
            )

    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert not tmp_file.exists()


def test_in_memory_cache_reads_from_disk_only_once(isolated_vault: None, tmp_path: Path) -> None:
    session_key = "cache:session"
    path = tmp_path / "cache_session.json"
    path.write_text(
        json.dumps(
            {
                "original_to_placeholder": {"Alice": "<<PERSON_1>>"},
                "placeholder_to_original": {"<<PERSON_1>>": "Alice"},
                "counters": {"PERSON": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with patch.object(io, "open", wraps=io.open) as mock_open:
        first = vault.get_map(session_key)
        second = vault.get_map(session_key)

    assert first == second
    assert mock_open.call_count == 1


def test_load_map_prunes_placeholder_to_placeholder_entries(
    isolated_vault: None,
    tmp_path: Path,
) -> None:
    session_key = "prune:session"
    path = tmp_path / "prune_session.json"
    path.write_text(
        json.dumps(
            {
                "original_to_placeholder": {
                    "Alice": "<<PERSON_1>>",
                    "<<PERSON_1>>": "<<PERSON_2>>",
                    "$<<AMOUNT_1>>": "<<AMOUNT_2>>",
                },
                "placeholder_to_original": {
                    "<<PERSON_1>>": "Alice",
                    "<<PERSON_2>>": "<<PERSON_1>>",
                    "<<AMOUNT_2>>": "$<<AMOUNT_1>>",
                },
                "counters": {"PERSON": 2},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    loaded = vault.get_map(session_key)

    assert loaded.original_to_placeholder == {"Alice": "<<PERSON_1>>"}
    assert loaded.placeholder_to_original == {"<<PERSON_1>>": "Alice"}


def test_replace_known_originals_swaps_existing_aliases_without_new_counters(
    isolated_vault: None,
) -> None:
    smap = _SessionMap()
    placeholder, _ = smap.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="turn-1")
    smap.register_alias(placeholder, "Alice", turn_id="turn-2")

    replaced, modified = smap.replace_known_originals("Alice sent a note to Alice Chen.")

    assert modified is True
    assert replaced == "<<PERSON_1>> sent a note to <<PERSON_1>>."
    assert smap.counters == {"PERSON": 1}
