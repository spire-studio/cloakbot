"""[Cap B] Scoped / keyed Vaults with strict session isolation.

These are the plan's Cap B acceptance tests (docs/exec-plans/active/nanobot-rebase.md,
row B):

  * an ephemeral ``/goal`` / ``dream`` map is NEVER written to the parent
    ``maps/{user}.json`` file;
  * a cross-scope restore is a no-op (an ephemeral run cannot resolve a parent
    placeholder back to its raw value);
  * ``/goal`` placeholders minted in an ephemeral run never land in the user
    vault file on disk.

The vault keeps its flat string API (``get_map`` / ``save_map`` /
``clear_cache``) for upstream call sites; Cap B routes those through the active
:class:`VaultScope`. ``shared`` scopes are disk-backed (the default, unchanged);
``ephemeral`` scopes are memory-only and dropped at run end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import cloakbot.privacy.core.state.vault as vault
from cloakbot.privacy.core.sanitization.restorer import restore_tokens
from cloakbot.privacy.core.state.vault import (
    VaultScope,
    active_ephemeral_run_key,
    drop_scope,
    ephemeral_scope,
    get_map,
    register_scope,
    resolve_scope,
    route_fixed_key_through_active_run,
    save_map,
    set_vault_workspace,
    shared_scope,
    use_ephemeral_scope,
)


@pytest.fixture()
def real_vault(tmp_path: Path):
    """Point the vault at a real on-disk workspace and reset all caches."""
    set_vault_workspace(tmp_path)
    vault._cache.clear()
    vault._ephemeral_cache.clear()
    vault._routes().clear()
    yield tmp_path
    vault._cache.clear()
    vault._ephemeral_cache.clear()
    vault._routes().clear()


def _maps_dir(workspace: Path) -> Path:
    return workspace / "privacy_vault" / "maps"


def _disk_files(workspace: Path) -> list[str]:
    maps = _maps_dir(workspace)
    if not maps.exists():
        return []
    return sorted(p.name for p in maps.iterdir() if p.is_file())


# --------------------------------------------------------------------------- #
# VaultScope identity
# --------------------------------------------------------------------------- #


def test_shared_scope_storage_key_is_bare_session_key() -> None:
    scope = shared_scope("tg:42")
    assert scope.isolation == "shared"
    assert scope.persistent is True
    # storage_key == session_key so maps/{key}.json is byte-for-byte unchanged.
    assert scope.storage_key == "tg:42"


def test_ephemeral_scope_storage_key_is_namespaced_off_root() -> None:
    scope = ephemeral_scope("tg:42", scope_kind="run", scope_id="abc")
    assert scope.isolation == "ephemeral"
    assert scope.persistent is False
    assert scope.storage_key == "tg:42#run#abc"
    # Two ephemeral scopes under the same parent are distinct vaults.
    other = ephemeral_scope("tg:42", scope_kind="run", scope_id="def")
    assert other.storage_key != scope.storage_key


def test_resolve_scope_defaults_to_shared() -> None:
    assert resolve_scope("tg:42") == shared_scope("tg:42")


# --------------------------------------------------------------------------- #
# Acceptance 1: ephemeral map never written to the parent file
# --------------------------------------------------------------------------- #


def test_ephemeral_run_map_never_written_to_disk(real_vault: Path) -> None:
    parent_key = "tg:owner"

    # The parent (persistent user) vault writes to disk as usual.
    parent = get_map(parent_key)
    parent.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="t0")
    save_map(parent_key, parent)
    assert _disk_files(real_vault) == ["tg_owner.json"]

    # An ephemeral run keyed off the same parent mints + saves placeholders...
    with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="run-1"):
        smap = get_map(parent_key)
        ph, is_new = smap.get_or_create_placeholder("0118 999 881 999 119 7253", "PHONE", turn_id="t1")
        assert is_new is True
        save_map(parent_key, smap)
        # ...but nothing new touches disk.
        assert _disk_files(real_vault) == ["tg_owner.json"]

    # After the run ends the ephemeral map is dropped entirely.
    assert vault._ephemeral_cache == {}
    # The parent's on-disk file is untouched by the ephemeral run.
    assert _disk_files(real_vault) == ["tg_owner.json"]
    on_disk = (real_vault / "privacy_vault" / "maps" / "tg_owner.json").read_text(encoding="utf-8")
    assert "PHONE" not in on_disk
    assert "999 119 7253" not in on_disk


def test_ephemeral_run_does_not_inherit_parent_placeholders(real_vault: Path) -> None:
    parent_key = "tg:owner"
    parent = get_map(parent_key)
    parent.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="t0")
    save_map(parent_key, parent)

    # Inside the ephemeral scope the map starts EMPTY — the parent's known
    # originals are not visible, so the run cannot re-mint or leak them.
    with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="run-1"):
        smap = get_map(parent_key)
        assert smap.original_to_placeholder == {}
        assert smap.placeholder_to_original == {}


# --------------------------------------------------------------------------- #
# Acceptance 2: cross-scope restore is a no-op
# --------------------------------------------------------------------------- #


def test_cross_scope_restore_is_a_noop(real_vault: Path) -> None:
    parent_key = "tg:owner"
    parent = get_map(parent_key)
    ph, _ = parent.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="t0")
    save_map(parent_key, parent)

    # In the parent (shared) scope the placeholder restores to the raw value.
    assert restore_tokens(ph, get_map(parent_key)) == "Alice Chen"

    # In an ephemeral child scope the placeholder is unknown, so restoring it
    # returns the placeholder unchanged — the raw value never crosses the scope.
    with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="run-1"):
        restored = restore_tokens(ph, get_map(parent_key))
        assert restored == ph
        assert "Alice Chen" not in restored


def test_distinct_ephemeral_scopes_do_not_share_placeholders(real_vault: Path) -> None:
    parent_key = "tg:owner"

    with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="run-a"):
        a = get_map(parent_key)
        a.get_or_create_placeholder("Secret A", "PERSON", turn_id="ta")
        save_map(parent_key, a)

    # A different ephemeral run (different scope_id) cannot see run-a's mapping.
    with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="run-b"):
        b = get_map(parent_key)
        assert b.lookup_placeholder("Secret A") is None
        assert restore_tokens("<<PERSON_1>>", b) == "<<PERSON_1>>"


# --------------------------------------------------------------------------- #
# Acceptance 3: /goal placeholders never in the user vault file
# --------------------------------------------------------------------------- #


def test_goal_objective_placeholders_never_in_user_vault_file(real_vault: Path) -> None:
    """An autonomous /goal-style run persists its own state, but its placeholder
    vault must not pollute the user's on-disk vault file."""
    user_key = "tg:owner"

    # The user vault has one known entity already.
    user = get_map(user_key)
    user.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="t0")
    save_map(user_key, user)
    user_file = real_vault / "privacy_vault" / "maps" / "tg_owner.json"
    before = user_file.read_text(encoding="utf-8")

    # An ephemeral /goal run mints a brand-new placeholder for a fresh entity
    # (e.g. an objective mentioning a new SSN) and saves its map.
    with use_ephemeral_scope(user_key, scope_kind="goal", scope_id="goal-1"):
        goal_map = get_map(user_key)
        goal_map.get_or_create_placeholder("123-45-6789", "SSN", turn_id="g1")
        save_map(user_key, goal_map)

    after = user_file.read_text(encoding="utf-8")
    # The user's on-disk vault is byte-for-byte unchanged by the goal run.
    assert after == before
    assert "SSN" not in after
    assert "123-45-6789" not in after
    # No stray ephemeral file was created on disk either.
    assert _disk_files(real_vault) == ["tg_owner.json"]


# --------------------------------------------------------------------------- #
# Scope routing lifecycle
# --------------------------------------------------------------------------- #


def test_register_and_drop_scope_round_trip(real_vault: Path) -> None:
    parent_key = "tg:owner"
    scope = ephemeral_scope(parent_key, scope_kind="run", scope_id="run-1")

    assert resolve_scope(parent_key).persistent is True
    register_scope(scope)
    assert resolve_scope(parent_key) == scope
    # A seeded empty memory map exists for the ephemeral scope.
    assert scope.storage_key in vault._ephemeral_cache

    drop_scope(scope)
    assert resolve_scope(parent_key).persistent is True
    assert scope.storage_key not in vault._ephemeral_cache


def test_registering_shared_scope_clears_any_active_route(real_vault: Path) -> None:
    parent_key = "tg:owner"
    register_scope(ephemeral_scope(parent_key, scope_kind="run", scope_id="run-1"))
    assert resolve_scope(parent_key).persistent is False

    register_scope(shared_scope(parent_key))
    assert resolve_scope(parent_key) == shared_scope(parent_key)


def test_nested_ephemeral_scopes_restore_prior_route(real_vault: Path) -> None:
    parent_key = "tg:owner"
    with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="outer") as outer:
        assert resolve_scope(parent_key) == outer
        with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="inner") as inner:
            assert resolve_scope(parent_key) == inner
        # Exiting the inner scope restores the outer route.
        assert resolve_scope(parent_key) == outer
    # Exiting the outer scope restores the default (shared) route.
    assert resolve_scope(parent_key).persistent is True


def test_set_vault_workspace_change_clears_ephemeral_cache(real_vault: Path, tmp_path: Path) -> None:
    parent_key = "tg:owner"
    with use_ephemeral_scope(parent_key, scope_kind="run", scope_id="run-1"):
        smap = get_map(parent_key)
        smap.get_or_create_placeholder("x", "PERSON")
        save_map(parent_key, smap)
        assert vault._ephemeral_cache != {}
        # Switching workspace mid-run clears the memory-only cache too.
        set_vault_workspace(tmp_path / "other")
        assert vault._ephemeral_cache == {}


def test_default_scope_still_persists_to_disk(real_vault: Path) -> None:
    """Regression guard: the default (shared) scope behaves exactly as pre-Cap-B."""
    key = "tg:owner"
    smap = get_map(key)
    smap.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="t0")
    save_map(key, smap)

    # Re-read from disk via a cleared cache.
    vault._cache.clear()
    reloaded = get_map(key)
    assert reloaded.original_to_placeholder["Alice Chen"] == "<<PERSON_1>>"
    assert isinstance(resolve_scope(key), VaultScope)
    assert resolve_scope(key).persistent is True


# --------------------------------------------------------------------------- #
# M3: fixed-key provider seams (image_gen / compaction) route through the
#     active ephemeral run instead of writing maps/{fixed_key}.json to disk.
# --------------------------------------------------------------------------- #


def test_active_ephemeral_run_key_tracks_the_innermost_run(real_vault: Path) -> None:
    assert active_ephemeral_run_key() is None
    with use_ephemeral_scope("tg:owner", scope_kind="run", scope_id="r1"):
        assert active_ephemeral_run_key() == "tg:owner"
        with use_ephemeral_scope("tg:other", scope_kind="run", scope_id="r2"):
            assert active_ephemeral_run_key() == "tg:other"
        assert active_ephemeral_run_key() == "tg:owner"
    assert active_ephemeral_run_key() is None


def test_fixed_key_is_disk_backed_outside_an_ephemeral_run(real_vault: Path) -> None:
    """On a normal user turn, image_gen / compaction keep their shared scope."""
    with route_fixed_key_through_active_run("image_gen"):
        smap = get_map("image_gen")
        smap.get_or_create_placeholder("Acme Corp", "ORG", turn_id="t0")
        save_map("image_gen", smap)
    # No ephemeral run active -> the fixed key persisted to disk as before.
    assert "image_gen.json" in _disk_files(real_vault)


def test_image_gen_fixed_key_routes_into_active_ephemeral_run(real_vault: Path) -> None:
    """M3: an image generated inside an ephemeral run never lands on disk."""
    with use_ephemeral_scope("tg:dreamer", scope_kind="run", scope_id="dream-1"):
        with route_fixed_key_through_active_run("image_gen"):
            # While routed, the fixed key resolves to a memory-only ephemeral scope.
            assert resolve_scope("image_gen").persistent is False
            smap = get_map("image_gen")
            smap.get_or_create_placeholder("Bruce Wayne", "PERSON", turn_id="t0")
            save_map("image_gen", smap)

    # After both scopes close, NOTHING for image_gen was written to disk.
    assert "image_gen.json" not in _disk_files(real_vault)
    assert _disk_files(real_vault) == []
    # And the ephemeral fixed-key map was dropped.
    assert vault._ephemeral_cache == {}


def test_compaction_fixed_key_routes_into_active_ephemeral_run(real_vault: Path) -> None:
    """M3: compaction inside an ephemeral run never writes maps/compaction.json."""
    with use_ephemeral_scope("tg:dreamer", scope_kind="run", scope_id="dream-1"):
        with route_fixed_key_through_active_run("compaction"):
            smap = get_map("compaction")
            smap.get_or_create_placeholder("Clark Kent", "PERSON", turn_id="t0")
            save_map("compaction", smap)

    assert "compaction.json" not in _disk_files(real_vault)
    assert _disk_files(real_vault) == []
