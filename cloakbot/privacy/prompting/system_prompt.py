"""Build the privacy-mode system-prompt section (deployment-level, always-on).

Ownership note: this module is the *only* place that decides the content and the
activation of the privacy-mode banner. ``cloakbot/agent/context.py`` never imports
privacy and never inspects the vault — it only receives opaque text through its
``extra_sections`` seam. The off-switch is ``config.privacy.inject_system_prompt``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "privacy_mode.md"


@lru_cache(maxsize=1)
def _privacy_mode_text() -> str:
    """Load the static privacy-mode banner (cached for the process)."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def _injection_enabled() -> bool:
    """Whether the privacy-mode prompt should be injected for this deployment.

    Always-on by default; disabled only when ``config.privacy.inject_system_prompt``
    is explicitly ``false``. Cached for the process lifetime — this is a
    deployment-level switch, not a per-turn one. Tests reset it via
    ``_injection_enabled.cache_clear()``.
    """
    try:
        from cloakbot.config.loader import get_config_path, load_config

        if get_config_path().exists():
            return bool(load_config().privacy.inject_system_prompt)
    except Exception:
        # A config read must never break prompt assembly — default to on.
        pass
    return True


def privacy_mode_active() -> bool:
    """Return True when the privacy-mode system prompt is enabled."""
    return _injection_enabled()


def build_privacy_system_section() -> str | None:
    """Return the privacy-mode system-prompt section, or None when disabled.

    The text is static (no per-session placeholder roster): it tells the model
    that ``<<TYPE_N>>`` tokens are real, locally-restored values it must use
    directly instead of treating them as fake placeholders. Returning None leaves
    the system prompt byte-for-byte identical to upstream.
    """
    if not privacy_mode_active():
        return None
    return _privacy_mode_text()
