"""Explicit egress classification for tools (Cap C).

The runner asks ``_tool_privacy_class`` what trust class a tool belongs to.
Historically that read a ``privacy_class`` attribute off the tool and defaulted
to :data:`ToolPrivacyClass.LOCAL` when absent. After the upstream rebase the
tool set grew (``apply_patch``, ``run_cli_app``, ``exec``/``list_exec_sessions``,
``my``/self-inspection, ``generate_image``, loader, plus new channels and any
MCP-shaped tool), so a missing tag silently means "LOCAL == safe to feed raw
restored arguments" — which is exactly the wrong default for a network egress.

This module is an **additive fall-through**: it classifies a tool by name/pattern
so a NEW upstream tool (or a user-registered CLI app) can never silently
mis-classify as LOCAL. It is consulted only when the tool itself declares no
explicit ``privacy_class`` attribute (the per-tool tag still wins).

Design rules (D1, 2026-06-04):

- Network / MCP-shaped tools default to ``EXTERNAL`` **and require approval**.
- Filesystem-shaped tools default to ``LOCAL`` (no approval).
- Side-effecting local tools (write/edit/patch/exec/cron/message) default to
  ``SIDE_EFFECT``.
- ``run_cli_app`` (CLI-Anything / arbitrary user-registered CLI apps) defaults to
  ``EXTERNAL`` + approval and is gated by an explicit per-app allow-list; no
  auto-install from model output, and egress is logged by the caller.
- Anything unrecognized is treated as a network egress (``EXTERNAL`` + approval)
  — fail-closed, never ``LOCAL``-by-omission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from loguru import logger

from cloakbot.tool_privacy import ToolPrivacyClass


@dataclass(frozen=True)
class ToolEgressDecision:
    """Classification result for one tool name."""

    privacy_class: ToolPrivacyClass
    requires_approval: bool
    reason: str

    def __post_init__(self) -> None:  # pragma: no cover - dataclass guard
        if not isinstance(self.privacy_class, ToolPrivacyClass):
            object.__setattr__(self, "privacy_class", ToolPrivacyClass(str(self.privacy_class)))


# --- name patterns ----------------------------------------------------------
# MCP tools are namespaced ``mcp_<server>_<tool>`` (see agent/tools/mcp.py); any
# such name is remote by construction.
_MCP_PREFIX = "mcp_"

# Explicit, known LOCAL filesystem / read-only inspection tools. Reads of the
# local tree never leave the host.
_LOCAL_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "list_dir",
        "find_files",
        "grep",
        "file_state",
    }
)

# Local side-effecting tools: mutate the host but do not egress. They still get a
# distinct class so callers can treat them differently from pure reads.
_SIDE_EFFECT_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "apply_patch",
        "exec",
        "list_exec_sessions",
        "cron",
        "message",
        "spawn",
        "long_task",
        "complete_goal",
        "my",
        "loader",
    }
)

# Known network / egress tools: send data to a remote endpoint.
_EXTERNAL_TOOLS: frozenset[str] = frozenset(
    {
        "web_fetch",
        "web_search",
        "generate_image",
    }
)

# CLI-Anything / user-registered CLI apps (D1): EXTERNAL + approval + allow-list.
_CLI_APP_TOOLS: frozenset[str] = frozenset({"run_cli_app"})

# Name fragments that strongly imply network egress even for tools we have never
# seen before. Ordered most-specific first is not required (substring scan).
_NETWORK_NAME_HINTS: tuple[str, ...] = (
    "web_",
    "_web",
    "http",
    "fetch",
    "search",
    "browse",
    "crawl",
    "remote",
    "upload",
    "download",
    "publish",
    "post_",
    "api_",
    "url",
    "image_gen",
    "generate_image",
)

# Name fragments that imply a purely local filesystem read.
_LOCAL_NAME_HINTS: tuple[str, ...] = (
    "read_file",
    "list_dir",
    "find_file",
    "grep",
    "glob",
    "stat_",
    "file_state",
)


@dataclass
class EgressPolicy:
    """Registry that maps a tool name to an :class:`ToolEgressDecision`.

    The policy is consulted only as a *fall-through* — explicit ``privacy_class``
    attributes on a tool always win in the runner. The default registry encodes
    the known tool set; ``register`` lets callers add overrides without forking.
    """

    overrides: dict[str, ToolEgressDecision] = field(default_factory=dict)
    # Per-app allow-list for ``run_cli_app`` (D1). Empty = nothing allowed, every
    # call needs approval and is rejected by the gate unless explicitly listed.
    cli_app_allowlist: frozenset[str] = field(default_factory=frozenset)

    def register(
        self,
        name: str,
        privacy_class: ToolPrivacyClass,
        *,
        requires_approval: bool = False,
        reason: str = "explicit override",
    ) -> None:
        """Register an explicit decision for *name* (highest precedence here)."""
        self.overrides[name] = ToolEgressDecision(
            privacy_class=privacy_class,
            requires_approval=requires_approval,
            reason=reason,
        )

    def decision_for(self, tool_name: str) -> ToolEgressDecision:
        """Classify *tool_name*, fail-closed to EXTERNAL+approval when unknown."""
        name = (tool_name or "").strip()
        if not name:
            return ToolEgressDecision(
                ToolPrivacyClass.EXTERNAL, True, "empty tool name -> fail-closed external"
            )

        override = self.overrides.get(name)
        if override is not None:
            return override

        if name in _CLI_APP_TOOLS:
            return ToolEgressDecision(
                ToolPrivacyClass.EXTERNAL,
                True,
                "cli-app (CLI-Anything): external + approval + per-app allow-list",
            )

        if name.startswith(_MCP_PREFIX):
            return ToolEgressDecision(
                ToolPrivacyClass.EXTERNAL, True, "mcp-namespaced tool -> external + approval"
            )

        if name in _EXTERNAL_TOOLS:
            return ToolEgressDecision(
                ToolPrivacyClass.EXTERNAL, True, "known network tool -> external + approval"
            )

        if name in _LOCAL_TOOLS:
            return ToolEgressDecision(ToolPrivacyClass.LOCAL, False, "known filesystem read")

        if name in _SIDE_EFFECT_TOOLS:
            return ToolEgressDecision(
                ToolPrivacyClass.SIDE_EFFECT, False, "known local side-effecting tool"
            )

        lower = name.lower()
        if any(hint in lower for hint in _NETWORK_NAME_HINTS):
            return ToolEgressDecision(
                ToolPrivacyClass.EXTERNAL,
                True,
                "network-shaped name -> safe default external + approval",
            )
        if any(hint in lower for hint in _LOCAL_NAME_HINTS):
            return ToolEgressDecision(
                ToolPrivacyClass.LOCAL, False, "filesystem-shaped name -> local"
            )

        # Unknown shape: fail-closed. Never default an unrecognized tool to LOCAL,
        # since a missing tag on a future egress tool would otherwise leak.
        return ToolEgressDecision(
            ToolPrivacyClass.EXTERNAL,
            True,
            "unrecognized tool -> fail-closed external + approval",
        )

    def classify(self, tool: object | None) -> ToolPrivacyClass:
        """Return the :class:`ToolPrivacyClass` for *tool* (object or name).

        Accepts either a tool instance (reads its ``name``) or a bare string,
        so it slots straight into ``_tool_privacy_class``'s fall-through.
        """
        name = self._name_of(tool)
        return self.decision_for(name).privacy_class

    def requires_approval(self, tool: object | None) -> bool:
        return self.decision_for(self._name_of(tool)).requires_approval

    def cli_app_allowed(self, app_name: str) -> bool:
        """True when *app_name* is on the explicit per-app allow-list (D1)."""
        return (app_name or "").strip() in self.cli_app_allowlist

    @staticmethod
    def _name_of(tool: object | None) -> str:
        if tool is None:
            return ""
        if isinstance(tool, str):
            return tool
        name = getattr(tool, "name", None)
        return str(name) if name else ""


def build_egress_policy(cli_app_allowlist: Iterable[str] | None = None) -> EgressPolicy:
    """Construct an :class:`EgressPolicy` with an optional CLI-app allow-list."""
    allowlist = frozenset(a.strip() for a in (cli_app_allowlist or []) if a and a.strip())
    return EgressPolicy(cli_app_allowlist=allowlist)


# Process-wide default policy used by the runner fall-through. Cheap, stateless
# for the common (no-override) path; callers that need a per-config allow-list
# build their own via :func:`build_egress_policy`.
_DEFAULT_POLICY = EgressPolicy()


def default_egress_policy() -> EgressPolicy:
    """Return the shared default policy (no CLI-app allow-list)."""
    return _DEFAULT_POLICY


def log_cli_app_egress(app_name: str, *, allowed: bool, session_key: str | None = None) -> None:
    """Audit-log a CLI-app egress decision (D1: egress logged)."""
    logger.bind(privacy="egress").info(
        "cli-app egress {} app={!r} session={!r}",
        "allowed" if allowed else "rejected",
        app_name,
        session_key,
    )


__all__ = [
    "EgressPolicy",
    "ToolEgressDecision",
    "build_egress_policy",
    "default_egress_policy",
    "log_cli_app_egress",
]
