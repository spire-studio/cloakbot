"""Additive consolidation-boundary wiring for Cap D.

``agent/memory.py`` ``Consolidator.archive`` summarizes an evicted window of
session messages by calling ``self.provider.chat_with_retry(...)`` and persists
the returned summary to ``history.jsonl`` (re-injected into future prompts). Cap
D must guard *that one call* — assert the window is tokenized before it reaches
the summarizer, and validate/repair the summary before it is persisted — without
forking ``Consolidator`` or ``AutoCompact``.

The seam is the consolidator's injected ``provider``. :class:`CompactionGuardedProvider`
is a transparent delegating wrapper: every attribute and method is forwarded to
the wrapped provider, except ``chat_with_retry``, which it brackets with a
:class:`~cloakbot.privacy.compaction.CompactionGuard`. ``install_compaction_guard``
swaps the consolidator's provider for the wrapped one — a one-call additive hook,
re-applied wherever the consolidator's provider is (re)assigned (``__init__`` /
``set_provider``), analogous to the Cap C provider-factory egress gate.

Fail-closed contract: when the guard rejects the summary (foreign / renumbered
placeholder or a raw value that could not be repaired), the wrapper returns an
``finish_reason="error"`` response. ``Consolidator.archive`` already treats an
errored summary as a degraded LLM call and falls back to ``raw_archive`` — i.e.
it keeps the **un-summarized** history rather than persisting a corrupt summary.
Pre-summarize tokenization failure (detector unavailable) propagates as a raised
exception, which ``archive``'s own ``try/except`` likewise routes to
``raw_archive``.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from cloakbot.privacy.compaction import CompactionGuard
from cloakbot.providers.base import LLMResponse

# Session key the consolidation summarizer runs under. The consolidator is not
# turn-scoped, so there is no per-turn session_key in scope at archive() time;
# the compaction window is the user's own replayed history, so it validates
# against the user's shared vault. A dedicated stable key keeps the contract
# explicit and routable through the Cap B scope table.
_COMPACTION_SESSION_KEY = "compaction"


def _window_text_from_messages(messages: list[dict[str, Any]]) -> str:
    """Concatenate the user-role content of a summarize request (the window)."""
    parts: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


def _replace_user_window(messages: list[dict[str, Any]], safe_text: str) -> list[dict[str, Any]]:
    """Return *messages* with the (single) user window content replaced.

    The consolidator always builds exactly one user message (the formatted
    window) plus a system instruction, so a single substitution is faithful.
    """
    out: list[dict[str, Any]] = []
    replaced = False
    for msg in messages:
        if (
            not replaced
            and isinstance(msg, dict)
            and msg.get("role") == "user"
            and isinstance(msg.get("content"), str)
        ):
            out.append({**msg, "content": safe_text})
            replaced = True
        else:
            out.append(msg)
    return out


class CompactionGuardedProvider:
    """Delegating provider that brackets summarize calls with the Cap D guard."""

    def __init__(self, inner: Any, *, session_key: str = _COMPACTION_SESSION_KEY) -> None:
        self._inner = inner
        self._session_key = session_key

    # Transparent delegation for everything the consolidator touches besides the
    # one guarded method (``.generation``, ``.chat``, retry internals, etc.).
    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def inner(self) -> Any:
        return self._inner

    async def chat_with_retry(
        self,
        messages: list[dict[str, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> LLMResponse:
        from cloakbot.privacy.core.state.vault import route_fixed_key_through_active_run

        guard = CompactionGuard(self._session_key)
        window = _window_text_from_messages(messages)

        # [Cap B / M3] The compaction seam uses a fixed shared key
        # (``compaction``). If compaction is triggered inside an ephemeral run
        # (dream / cron / heartbeat), route the guard's placeholder bookkeeping
        # into that run's memory-only ephemeral scope so it never lands at
        # maps/compaction.json on disk. No-op on normal user turns.
        with route_fixed_key_through_active_run(self._session_key):
            # Pre-summarize: sanitize-or-fail-closed. A detector-unavailable
            # failure raises out of here; archive() catches it and raw-archives.
            safe_input = await guard.prepare(window)
            guarded_messages = _replace_user_window(messages, safe_input)

            response = await self._inner.chat_with_retry(guarded_messages, *args, **kwargs)
            if response.finish_reason == "error":
                return response

            result = await guard.finalize(response.content)
        if not result.accepted:
            logger.bind(privacy="compaction").warning(
                "compaction: summary rejected ({}); keeping un-summarized history",
                result.reason,
            )
            return LLMResponse(
                content=f"[compaction summary rejected: {result.reason}]",
                finish_reason="error",
            )

        # Replace the summary content with the validated/repaired text. Rebuild
        # rather than mutate so callers holding the original response are
        # unaffected (LLMResponse may be frozen / shared).
        return _with_content(response, result.summary)


def _with_content(response: LLMResponse, content: str | None) -> LLMResponse:
    """Return a copy of *response* with replaced content (dataclass-agnostic)."""
    try:
        import dataclasses

        if dataclasses.is_dataclass(response):
            return dataclasses.replace(response, content=content)
    except Exception:  # pragma: no cover - dataclasses.replace edge
        pass
    try:
        response.content = content  # type: ignore[misc]
        return response
    except Exception:  # pragma: no cover - frozen + non-dataclass
        return LLMResponse(content=content, finish_reason=response.finish_reason)


def install_compaction_guard(consolidator: Any) -> None:
    """Wrap *consolidator*'s provider with the Cap D guard (idempotent).

    Additive hook: call after the consolidator is constructed and after any
    ``set_provider`` swap. A no-op if the provider is already guarded.
    """
    provider = getattr(consolidator, "provider", None)
    if provider is None or isinstance(provider, CompactionGuardedProvider):
        return
    consolidator.provider = CompactionGuardedProvider(provider)


__all__ = [
    "CompactionGuardedProvider",
    "install_compaction_guard",
]
