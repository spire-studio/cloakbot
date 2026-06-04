"""At-rest sanitizer for sustained-goal objectives (Cap C).

``/goal`` objectives are persisted on the session under
``metadata['goal_state']['objective']`` and mirrored into the Runtime Context
block every turn. The ``long_task`` tool receives *restored* arguments (tools run
against real values locally), so the objective text it stores can contain raw
sensitive values. Persisting that raw text is an at-rest leak: it would survive
across turns and be re-injected into future prompts before the per-turn detector
runs — once per turn, indefinitely.

This helper runs the objective through the **real per-turn detector**
(:func:`sanitize_input_with_detection`) so a not-yet-minted raw value (one the
session has never seen before — e.g. a name typed directly into ``/goal``) is
still detected and tokenized, not just the already-known surface forms. It is
**fail-closed**: if the local detector is unavailable, it does NOT fall back to
persisting the raw objective (the old behavior, which silently swallowed the
error and re-injected raw PII every turn). Instead it raises
:class:`GoalSanitizationError` so the caller refuses to register the goal rather
than write an un-sanitized objective to disk.

Restoration for display happens through the normal vault path, so a successfully
placeholdered objective is loss-free when shown back to the user.
"""

from __future__ import annotations

from cloakbot.privacy.core.sanitization.sanitize import sanitize_input_with_detection


class GoalSanitizationError(RuntimeError):
    """Raised when a ``/goal`` objective cannot be safely sanitized at rest.

    The caller MUST NOT persist the raw objective when this is raised — doing so
    would re-inject un-detected PII into every future prompt. Refuse the goal (or
    drop the objective) instead.
    """


async def sanitize_goal_objective(session_key: str | None, objective: str | None) -> str:
    """Return *objective* tokenized via the per-turn detector (fail-closed).

    * Empty / session-less objectives pass through unchanged (nothing to leak).
    * Otherwise the objective is routed through
      :func:`sanitize_input_with_detection` with ``fail_open=False`` so a
      not-yet-minted raw value is detected and replaced by a stable placeholder.
    * On detector unavailability the underlying call raises; we surface it as
      :class:`GoalSanitizationError` so the caller declines to persist raw text.
    """
    if not objective or not session_key:
        return objective or ""
    try:
        sanitized, _modified, _entities, _detection = await sanitize_input_with_detection(
            objective,
            session_key,
            fail_open=False,
        )
    except Exception as exc:  # noqa: BLE001 - any detector failure must fail closed
        raise GoalSanitizationError(
            "goal objective could not be sanitized (privacy detector unavailable); "
            "refusing to persist raw objective"
        ) from exc
    return sanitized


__all__ = ["GoalSanitizationError", "sanitize_goal_objective"]
