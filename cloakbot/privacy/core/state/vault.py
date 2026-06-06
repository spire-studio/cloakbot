"""Session map storage for privacy placeholder vaults."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from cloakbot.config.paths import get_workspace_path


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


# ---------------------------------------------------------------------------
# [Cap B] Scoped / keyed Vaults with strict session isolation.
#
# Upstream keys all privacy state on a flat ``session_key`` string and writes it
# to ``maps/{session_key}.json``. That is correct for *persistent user turns*,
# but several derived run paths construct a child run that keys off the parent's
# ``session_key`` (``/goal`` long tasks, ``dream`` refactors, ``cron`` callbacks,
# and ``pairing``). If those ephemeral runs reused the parent vault, placeholder
# mappings minted during an autonomous run (or the parent's raw originals) would
# be written into the user's on-disk vault file and could bleed across runs.
#
# Cap B introduces ``VaultScope`` so each run declares its isolation:
#   * ``shared``     — the persistent user vault, disk-backed at maps/{key}.json
#                      (the default; preserves all existing behavior exactly).
#   * ``ephemeral``  — a memory-only child scope. Its map is NEVER ``_save_map``'d
#                      to the parent file and is dropped at run end. Restores of a
#                      parent placeholder inside an ephemeral scope are a no-op
#                      because the ephemeral map starts empty (cross-scope
#                      restore = no-op).
#
# AT-REST COVERAGE (exactly which run paths get an ephemeral scope, verified
# against the call sites — keep this list honest):
#   * ``dream``     — ``cli/commands.py`` ``on_cron_job`` dispatches the dream
#                     consolidation with ``process_direct(..., ephemeral=True)``;
#                     no ``maps/dream*.json`` is written.
#   * ``cron``      — the generic cron reminder dispatch
#                     (``process_direct(session_key="cron:{job.id}",
#                     ephemeral=True)``) runs in an ephemeral scope; no
#                     ``maps/cron_<id>.json`` is written.
#   * ``heartbeat`` — the heartbeat job (``session_key="heartbeat"``,
#                     ``ephemeral=True``) runs in an ephemeral scope; no
#                     ``maps/heartbeat.json`` is written. (Heartbeat is a
#                     fork-era feature; the call is kept ephemeral, not removed.)
#
# Each of the above is plumbed through ``AgentLoop._process_message``: when
# ``ephemeral=True`` it wraps the turn state machine in ``use_ephemeral_scope``.
#
# NOT routed through an ephemeral scope (by design, not a gap):
#   * ``/goal`` (``long_task``) — runs inside the *parent* user turn against the
#     shared vault; its persisted objective is placeholdered at rest by the Cap C
#     ``goal_at_rest`` sanitizer rather than isolated to a throwaway scope.
#   * ``spawn`` — constructs its OWN ``session_key`` (``spawn_session_key``
#     ContextVar, defaulting ``cli:direct``), so a spawned subagent never flatly
#     reuses the parent vault file.
#   * ``pairing`` — ``pairing/store.py`` is a synchronous command handler; it
#     never calls ``process_direct`` and never opens a session-key vault run, so
#     there is no placeholder map to isolate.
#
# The fixed-key provider seams (image-gen ``"image_gen"``, compaction
# ``"compaction"``) are *also* routed into the active ephemeral scope when the
# parent run is ephemeral — see ``active_ephemeral_run_key`` below.
# ---------------------------------------------------------------------------

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
_workspace: Path | None = None


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
    global _workspace
    next_workspace = Path(workspace).expanduser()
    if _workspace != next_workspace:
        _cache.clear()
        _ephemeral_cache.clear()
    _workspace = next_workspace


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
        _cache[key] = _load_map(key)
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
    _save_map(key, smap)
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
    safe = _safe_key(session_key)
    vault_dir = get_privacy_vault_dir(_workspace)
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
