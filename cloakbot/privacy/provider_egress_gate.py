"""Provider-layer egress gate for sanitized HIGH-entity prompts (Cap C).

``FallbackProvider`` transparently fails a request over to a chain of fallback
models that may live on *different endpoints*. That is operationally useful but a
privacy hazard: a prompt that was only safe to send remotely *because* it was
sanitized still carries HIGH-severity placeholders (``<<SSN_1>>``,
``<<CREDENTIAL_1>>``, …). The placeholders themselves are not raw, but routing a
HIGH-entity turn to an arbitrary, operator-unvetted fallback endpoint widens the
trust surface beyond what the user configured.

This gate is an additive subclass of ``FallbackProvider``. When the outgoing
prompt contains a HIGH-severity placeholder, fallbacks are restricted to an
explicit allow-list (source = config). Non-allow-listed fallbacks are dropped
(and the decision logged) before the underlying failover even sees them; the
primary endpoint is always permitted because the user already chose it.

It never inspects or transmits raw values — it reasons purely about placeholder
tags already present in the sanitized payload.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from loguru import logger

from cloakbot.privacy.core.types import REGISTRY, Severity
from cloakbot.providers.base import LLMResponse
from cloakbot.providers.fallback_provider import FallbackProvider

# Matches a privacy placeholder token and captures its TAG (e.g. ``SSN`` from
# ``<<SSN_1>>``). Mirrors ``vault.PLACEHOLDER_RE`` but with a capture group.
_PLACEHOLDER_TAG_RE = re.compile(r"<<([A-Z]+(?:_[A-Z]+)*)_\d+>>")


def _high_severity_slugs() -> frozenset[str]:
    """Entity slugs whose severity is HIGH (keys into ``severity_map``)."""
    return frozenset(
        slug for slug, sev in REGISTRY.severity_map.items() if sev == Severity.HIGH
    )


_HIGH_SLUGS = _high_severity_slugs()


def prompt_has_high_severity_placeholder(messages: Any) -> bool:
    """True when *messages* contain at least one HIGH-severity placeholder tag."""
    text = _stringify_messages(messages)
    if not text:
        return False
    for match in _PLACEHOLDER_TAG_RE.finditer(text):
        tag = match.group(1)
        if tag.lower() in _HIGH_SLUGS:
            return True
    return False


def _stringify_messages(messages: Any) -> str:
    """Flatten chat messages / kwargs into a single scannable string."""
    if messages is None:
        return ""
    if isinstance(messages, str):
        return messages
    parts: list[str] = []
    if isinstance(messages, dict):
        messages = [messages]
    try:
        iterator: Iterable[Any] = iter(messages)
    except TypeError:
        return str(messages)
    for msg in iterator:
        if isinstance(msg, str):
            parts.append(msg)
            continue
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(block, str):
                    parts.append(block)
    return "\n".join(parts)


def fallback_endpoint_identifiers(fallback_preset: Any) -> set[str]:
    """Identifiers a fallback can be allow-listed under: model and provider."""
    out: set[str] = set()
    model = getattr(fallback_preset, "model", None)
    provider = getattr(fallback_preset, "provider", None)
    if model:
        out.add(str(model))
    if provider and str(provider) != "auto":
        out.add(str(provider))
    return out


class EgressGatedFallbackProvider(FallbackProvider):
    """``FallbackProvider`` that gates fallbacks for HIGH-entity sanitized prompts.

    *allowlist* is the set of fallback identifiers (model name or provider name)
    that remain eligible when the prompt carries a HIGH-severity placeholder.
    An empty allow-list means: a HIGH-entity turn may use **only** the primary
    endpoint the user configured; every fallback is dropped.
    """

    def __init__(
        self,
        primary: Any,
        fallback_presets: list[Any],
        provider_factory: Any,
        *,
        allowlist: Iterable[str] | None = None,
    ) -> None:
        super().__init__(primary, fallback_presets, provider_factory)
        self._egress_allowlist = frozenset(
            a.strip() for a in (allowlist or []) if a and a.strip()
        )

    def _gate_presets(self, messages: Any) -> tuple[list[Any], list[Any]]:
        """Split fallbacks into (permitted, blocked) for this request's prompt."""
        if not prompt_has_high_severity_placeholder(messages):
            return list(self._fallback_presets), []
        permitted: list[Any] = []
        blocked: list[Any] = []
        for preset in self._fallback_presets:
            ids = fallback_endpoint_identifiers(preset)
            if ids & self._egress_allowlist:
                permitted.append(preset)
            else:
                blocked.append(preset)
        return permitted, blocked

    async def _try_with_fallback(self, call: Any, kwargs: dict[str, Any], has_streamed: Any) -> LLMResponse:
        messages = kwargs.get("messages")
        permitted, blocked = self._gate_presets(messages)
        if blocked:
            for preset in blocked:
                logger.bind(privacy="egress").warning(
                    "fallback '{}' blocked for HIGH-entity sanitized prompt (not allow-listed)",
                    getattr(preset, "model", "?"),
                )
        if blocked and not permitted:
            # No eligible fallback remains: behave as a primary-only provider so
            # the HIGH-entity turn cannot route to an unvetted endpoint.
            saved = self._fallback_presets
            saved_has = self._has_fallbacks
            self._fallback_presets = []
            self._has_fallbacks = False
            try:
                return await super()._try_with_fallback(call, kwargs, has_streamed)
            finally:
                self._fallback_presets = saved
                self._has_fallbacks = saved_has
        if blocked:
            saved = self._fallback_presets
            self._fallback_presets = permitted
            try:
                return await super()._try_with_fallback(call, kwargs, has_streamed)
            finally:
                self._fallback_presets = saved
        return await super()._try_with_fallback(call, kwargs, has_streamed)


def wrap_with_egress_gate(
    provider: Any,
    *,
    allowlist: Iterable[str] | None = None,
) -> Any:
    """Re-wrap a ``FallbackProvider`` as an :class:`EgressGatedFallbackProvider`.

    Non-``FallbackProvider`` providers (no fallbacks configured) are returned
    unchanged — there is nothing to gate.
    """
    if not isinstance(provider, FallbackProvider):
        return provider
    if isinstance(provider, EgressGatedFallbackProvider):
        return provider
    gated = EgressGatedFallbackProvider(
        primary=provider._primary,
        fallback_presets=list(provider._fallback_presets),
        provider_factory=provider._provider_factory,
        allowlist=allowlist,
    )
    return gated


__all__ = [
    "EgressGatedFallbackProvider",
    "fallback_endpoint_identifiers",
    "prompt_has_high_severity_placeholder",
    "wrap_with_egress_gate",
]
