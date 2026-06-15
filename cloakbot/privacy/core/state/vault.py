"""Public facade for the privacy placeholder vault.

The vault is composed of three layers, each importable on its own but presented
here as one cohesive API so callers depend on "the vault", not its internals:

- :mod:`registry`     — the in-memory data model (:class:`_SessionMap`).
- :mod:`vault_store`  — workspace-scoped disk + artifact serialization.
- :mod:`scope`        — Cap B scope routing and live ``get_map`` / ``save_map``.

Import everything from here (``cloakbot.privacy.core.state.vault``). The
``<<TAG_N>>`` grammar itself lives in :mod:`cloakbot.privacy.core.placeholders`.
"""

from __future__ import annotations

from cloakbot.privacy.core.state import scope as _scope
from cloakbot.privacy.core.state.registry import (
    VaultComputation,
    VaultEntity,
    _SessionMap,
)
from cloakbot.privacy.core.state.scope import (
    Isolation,
    VaultScope,
    active_ephemeral_run_key,
    clear_cache,
    delete_session_vault,
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
from cloakbot.privacy.core.state.vault_store import (
    _load_map,
    _safe_key,
    _save_map,
    current_workspace,
    get_privacy_vault_dir,
    save_artifact_bytes,
    save_artifact_text,
)

# The live in-memory maps and route table are owned by ``scope``; the same
# objects are surfaced here so the vault subsystem's own tests can reset/inspect
# them through the facade. Not public API (underscored, absent from ``__all__``).
_cache = _scope._cache
_ephemeral_cache = _scope._ephemeral_cache
_routes = _scope._routes

__all__ = [
    "Isolation",
    "VaultComputation",
    "VaultEntity",
    "VaultScope",
    "_SessionMap",
    "_load_map",
    "_safe_key",
    "_save_map",
    "active_ephemeral_run_key",
    "clear_cache",
    "current_workspace",
    "delete_session_vault",
    "drop_scope",
    "ephemeral_scope",
    "get_map",
    "get_privacy_vault_dir",
    "register_scope",
    "resolve_scope",
    "route_fixed_key_through_active_run",
    "save_artifact_bytes",
    "save_artifact_text",
    "save_map",
    "set_vault_workspace",
    "shared_scope",
    "use_ephemeral_scope",
]
