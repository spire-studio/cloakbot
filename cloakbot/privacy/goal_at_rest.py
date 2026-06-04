"""At-rest sanitizer for sustained-goal objectives (Cap C).

``/goal`` objectives are persisted on the session under
``metadata['goal_state']['objective']`` and mirrored into the Runtime Context
block every turn. The ``long_task`` tool receives *restored* arguments (tools run
against real values locally), so the objective text it stores can contain raw
sensitive values. Persisting that raw text is an at-rest leak: it would survive
across turns and be re-injected into future prompts before the per-turn detector
runs.

This helper re-applies the **already-known** vault mappings for the session via
``replace_known_originals`` — a placeholder-only pass that needs no detector
call and never invents new entities. Raw surface forms the session has already
seen become stable placeholders; everything else is left untouched. Restoration
for display happens through the normal vault path, so this is loss-free.
"""

from __future__ import annotations

from cloakbot.privacy.core.state.vault import get_map


def sanitize_goal_objective(session_key: str | None, objective: str | None) -> str:
    """Return *objective* with known raw values swapped to stable placeholders.

    Fail-open: any vault error returns the input unchanged rather than dropping
    the objective (the per-turn pipeline remains the primary boundary).
    """
    if not objective or not session_key:
        return objective or ""
    try:
        smap = get_map(session_key)
        sanitized, _changed = smap.replace_known_originals(objective)
        return sanitized
    except Exception:
        return objective


__all__ = ["sanitize_goal_objective"]
