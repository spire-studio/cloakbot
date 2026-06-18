"""Scoped, session-isolated live access to placeholder maps (Cap B).

Upstream keys all privacy state on a flat ``session_key`` and writes it to
``maps/{session_key}.json``. That is correct for persistent user turns, but
several derived runs (``/goal``, ``dream``, ``cron``, ``heartbeat``) construct a
child run off the parent's key; if they reused the parent vault, placeholder
mappings minted during an autonomous run could bleed onto the user's disk vault.

A :class:`VaultScope` therefore declares each run's isolation:

- ``shared`` — the persistent user vault, disk-backed at ``maps/{key}.json``
  (the default; byte-for-byte the pre-Cap-B behaviour).
- ``ephemeral`` — a memory-only child scope, never written under the parent's
  map file and dropped at run end; a cross-scope restore is a no-op.

The full at-rest coverage table (which run paths get an ephemeral scope, and
why ``spawn`` / ``pairing`` don't need one) lives in ``docs/domains/privacy.md``
under "Vault Scopes (Cap B)". This module owns scope routing, the live in-memory
caches, and the ``get_map`` / ``save_map`` access facade; disk serialization is
in :mod:`vault_store` and the data model in :mod:`registry`.
"""

from __future__ import annotations

import contextlib
import shutil
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cloakbot.privacy.core.state import vault_store
from cloakbot.privacy.core.state.registry import _SessionMap

Isolation = Literal["shared", "ephemeral"]


@dataclass(frozen=True)
class VaultScope:
    """Identity + isolation policy for one vault.

    ``storage_key`` is the cache/disk identity. For ``shared`` scopes it is the
    bare ``root_session_key`` so the on-disk path stays ``maps/{root}.json`` and
    every pre-Cap-B call site is byte-for-byte unchanged. For ``ephemeral``
    scopes it is a namespaced key that no ``_map_path`` ever resolves to disk.
    """

    root_session_key: str
    scope_kind: str = "session"
    scope_id: str = ""
    isolation: Isolation = "shared"

    @property
    def storage_key(self) -> str:
        if self.isolation == "shared":
            return self.root_session_key
        return f"{self.root_session_key}#{self.scope_kind}#{self.scope_id}"

    @property
    def persistent(self) -> bool:
        return self.isolation == "shared"


def shared_scope(session_key: str) -> VaultScope:
    """The persistent user vault for ``session_key`` (the default scope)."""
    return VaultScope(root_session_key=session_key, scope_kind="session", isolation="shared")


def ephemeral_scope(
    root_session_key: str,
    *,
    scope_kind: str,
    scope_id: str,
) -> VaultScope:
    """A memory-only child scope keyed off ``root_session_key``.

    Used by autonomous / derived runs (``/goal``, ``dream``, ``cron``,
    ``pairing``) so their placeholder mappings never touch the parent's on-disk
    vault and are dropped when the run ends.
    """
    return VaultScope(
        root_session_key=root_session_key,
        scope_kind=scope_kind,
        scope_id=scope_id,
        isolation="ephemeral",
    )


# Persistent (disk-backed) maps, keyed by storage_key (== session_key for shared).
_cache: dict[str, _SessionMap] = {}
# Memory-only ephemeral maps, keyed by storage_key. Never written to disk and
# dropped on ``drop_scope`` / run end.
_ephemeral_cache: dict[str, _SessionMap] = {}
# Active scope routing: a bare session_key string addresses a scope. Default is
# the shared scope; an ephemeral run registers its key here for the run's
# duration. Thread-local so concurrent runs in the same process never collide.
_scope_routes = threading.local()


def _routes() -> dict[str, VaultScope]:
    table = getattr(_scope_routes, "table", None)
    if table is None:
        table = {}
        _scope_routes.table = table
    return table


def _active_ephemeral_runs() -> list[VaultScope]:
    """Stack of ephemeral *run* scopes active on this thread (innermost last).

    Distinct from the per-key ``_routes`` table: this records that an autonomous
    run (dream / cron / heartbeat) is in progress so the fixed-key provider seams
    (image-gen / compaction) — which address a DIFFERENT key than the run's
    ``root_session_key`` and so are not covered by the run's route — can opt into
    the same ephemeral isolation instead of writing ``maps/image_gen.json`` /
    ``maps/compaction.json`` to disk.
    """
    stack = getattr(_scope_routes, "ephemeral_runs", None)
    if stack is None:
        stack = []
        _scope_routes.ephemeral_runs = stack
    return stack


def active_ephemeral_run_key() -> str | None:
    """Return the innermost active ephemeral run's ``root_session_key``, if any.

    ``None`` when the current thread is running a normal (persistent) turn. Used
    by the fixed-key seams to decide whether to route through an ephemeral scope.
    """
    stack = _active_ephemeral_runs()
    return stack[-1].root_session_key if stack else None


def resolve_scope(session_key: str) -> VaultScope:
    """Return the active scope a bare ``session_key`` currently addresses."""
    return _routes().get(session_key, shared_scope(session_key))


def register_scope(scope: VaultScope) -> None:
    """Route ``scope.root_session_key`` to ``scope`` until it is dropped.

    Idempotent for shared scopes (a shared scope is the default, so registering
    one simply clears any prior route). Ephemeral scopes seed an empty
    memory-only map so the first ``get_map`` does not fall through to the
    parent's disk file (which would be a cross-scope leak).
    """
    routes = _routes()
    if scope.persistent:
        routes.pop(scope.root_session_key, None)
        return
    routes[scope.root_session_key] = scope
    _ephemeral_cache.setdefault(scope.storage_key, _SessionMap())


def drop_scope(scope: VaultScope) -> None:
    """Drop an ephemeral scope's memory-only map and restore the default route."""
    routes = _routes()
    if routes.get(scope.root_session_key) == scope:
        routes.pop(scope.root_session_key, None)
    if not scope.persistent:
        _ephemeral_cache.pop(scope.storage_key, None)


@contextlib.contextmanager
def use_ephemeral_scope(
    root_session_key: str,
    *,
    scope_kind: str,
    scope_id: str,
) -> Iterator[VaultScope]:
    """Activate a memory-only ephemeral scope for the duration of a run.

    Within the ``with`` block, every ``get_map(root_session_key)`` /
    ``save_map(root_session_key, ...)`` call resolves to the ephemeral child
    scope: its placeholder mappings live only in ``_ephemeral_cache`` and are
    dropped on exit (never written under ``maps/{root}.json``). The prior route
    (if any) is restored afterward so nested runs compose correctly.
    """
    scope = ephemeral_scope(root_session_key, scope_kind=scope_kind, scope_id=scope_id)
    routes = _routes()
    prior = routes.get(root_session_key)
    register_scope(scope)
    runs = _active_ephemeral_runs()
    runs.append(scope)
    try:
        yield scope
    finally:
        if runs and runs[-1] is scope:
            runs.pop()
        else:  # defensive: remove by identity if nesting got out of order
            with contextlib.suppress(ValueError):
                runs.remove(scope)
        drop_scope(scope)
        if prior is not None:
            routes[root_session_key] = prior


@contextlib.contextmanager
def route_fixed_key_through_active_run(fixed_key: str) -> Iterator[VaultScope]:
    """Route a fixed-key provider seam through the active ephemeral run, if any.

    The image-gen (``"image_gen"``) and compaction (``"compaction"``) seams use a
    stable shared key that is *not* the active run's ``root_session_key``, so an
    ephemeral run's route does not cover them. Without this, an image generated
    (or a compaction triggered) inside a dream/cron/heartbeat run would mint a
    placeholder map at ``maps/{fixed_key}.json`` on disk — outside the run's
    ephemeral scope (M3).

    When an ephemeral run is active on this thread, this wraps *fixed_key* in its
    own memory-only ephemeral scope (namespaced under the active run) for the
    duration of the ``with`` block, so its mappings live only in memory and are
    dropped at block exit. When no ephemeral run is active it is a no-op: the
    fixed key keeps its normal shared (disk-backed) scope, preserving the exact
    pre-Cap-B behavior for ordinary user turns.
    """
    run_key = active_ephemeral_run_key()
    if run_key is None:
        # Normal persistent turn: leave the fixed key on its shared scope.
        yield resolve_scope(fixed_key)
        return
    with use_ephemeral_scope(
        fixed_key,
        scope_kind="run-fixed",
        scope_id=run_key,
    ) as scope:
        yield scope


def set_vault_workspace(workspace: str | Path) -> None:
    if vault_store.set_workspace(workspace):
        _cache.clear()
        _ephemeral_cache.clear()


def get_map(session_key: str) -> _SessionMap:
    """Return the placeholder map addressed by ``session_key``.

    Routes through the active :class:`VaultScope`. For the default (shared)
    scope this lazily loads ``maps/{session_key}.json`` exactly as before. For an
    active ephemeral scope it returns the memory-only child map and never touches
    disk — so a parent placeholder that was never minted inside the ephemeral run
    is simply absent (cross-scope restore is a no-op).
    """
    scope = resolve_scope(session_key)
    if not scope.persistent:
        smap = _ephemeral_cache.get(scope.storage_key)
        if smap is None:
            smap = _SessionMap()
            _ephemeral_cache[scope.storage_key] = smap
        return smap

    key = scope.storage_key
    if key not in _cache:
        _cache[key] = vault_store._load_map(key)
    return _cache[key]


def save_map(session_key: str, smap: _SessionMap) -> None:
    """Persist (shared) or stash (ephemeral) the map addressed by ``session_key``.

    Shared scopes are written atomically to disk. **Ephemeral scopes are never
    written under the parent's ``maps/{root}.json``** — the map is kept in the
    memory-only cache and dropped at run end. This is the Cap B isolation
    guarantee: a ``/goal`` / ``dream`` / ``cron`` / ``pairing`` run cannot leak
    placeholder mappings into the user's on-disk vault.
    """
    scope = resolve_scope(session_key)
    if not scope.persistent:
        _ephemeral_cache[scope.storage_key] = smap
        return
    key = scope.storage_key
    vault_store._save_map(key, smap)
    _cache[key] = smap


def clear_cache(session_key: str) -> None:
    scope = resolve_scope(session_key)
    if not scope.persistent:
        _ephemeral_cache.pop(scope.storage_key, None)
        return
    _cache.pop(scope.storage_key, None)


def delete_session_vault(session_key: str) -> bool:
    """Cascade-delete all on-disk privacy state for *session_key*.

    Removes the placeholder map (``maps/{key}.json``), the per-turn WebUI privacy
    log (``turns/{key}.jsonl``), and any tool artifacts minted under this session
    (``artifacts/{key}/``), then evicts the in-memory cache. Called when a WebUI
    chat is deleted so the local vault never outlives the conversation it mirrors
    (the vault holds raw placeholder↔value mappings at rest).

    Best-effort and idempotent: missing files are ignored. Returns ``True`` if
    anything was removed.
    """
    clear_cache(session_key)
    safe = vault_store._safe_key(session_key)
    vault_dir = vault_store.get_privacy_vault_dir(vault_store.current_workspace())
    removed = False
    for path in (
        vault_dir / "maps" / f"{safe}.json",
        vault_dir / "turns" / f"{safe}.jsonl",
    ):
        if path.is_file():
            with contextlib.suppress(OSError):
                path.unlink()
                removed = True
    artifacts_dir = vault_dir / "artifacts" / safe
    if artifacts_dir.is_dir():
        with contextlib.suppress(OSError):
            shutil.rmtree(artifacts_dir)
            removed = True
    return removed


__all__ = [
    "Isolation",
    "VaultScope",
    "active_ephemeral_run_key",
    "clear_cache",
    "delete_session_vault",
    "drop_scope",
    "ephemeral_scope",
    "get_map",
    "register_scope",
    "resolve_scope",
    "route_fixed_key_through_active_run",
    "save_map",
    "set_vault_workspace",
    "shared_scope",
    "use_ephemeral_scope",
]
