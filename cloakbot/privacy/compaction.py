"""Placeholder-stable context compaction (Cap D).

The autocompact / consolidation boundary (``agent/memory.py`` ``Consolidator``
and ``agent/autocompact.py`` ``AutoCompact``) hands a window of older messages to
a remote summarizer LLM and folds the returned summary back into the durable
session history. Those messages have already crossed the privacy boundary as
*placeholdered* text (``<<TAG_N>>``), so the summarizer only ever sees tokens —
never raw values. But a summary is **model output over untrusted ground**, and
the model can do three damaging things to the token stream:

1. **Emit a raw value.** If a raw sensitive surface form ever reaches the
   summarizer (a pre-compaction sanitize miss, or a hand-fed string), the model
   can echo it verbatim into the summary, which is then *persisted at rest* and
   re-injected into every future prompt before the per-turn detector runs.
2. **Invent a foreign token.** The model can hallucinate ``<<PERSON_9>>`` for a
   placeholder that was never minted in this session's vault. Restoring that
   later resolves to nothing (or, worse, to a *different* entity if the counter
   later reaches 9), silently corrupting attribution.
3. **Renumber.** The model can rewrite ``<<PERSON_1>>`` as ``<<PERSON_2>>``
   (or collapse two distinct people onto one token). The summary still looks
   well-formed, but restoration now maps to the wrong human.

Cap D is a **compaction-aware vault contract** invoked as an *additive* bracket
around the summarizer call — it forks neither ``Consolidator`` nor
``AutoCompact``. It runs two checks against the **scoped** vault (Cap B):

* **pre-summarize** (:func:`assert_tokenized`): the text handed to the summarizer
  must already be tokenized. Fail-closed — if a raw sensitive surface is still
  present we tokenize it (so the summarizer never sees raw) rather than trusting
  the upstream pipeline blindly.
* **post-summarize** (:func:`validate_placeholders`): every ``<<TAG_N>>`` in the
  summary must (a) exist in the scoped vault and (b) be a member of the
  *pre-compaction* token set for this window — diffing the summary's token set
  against the input's token set is what forbids renumbering and foreign tokens.
  A summary that carries an orphan / foreign / renumbered token, or a raw value,
  is **repaired or rejected**: the offending span is re-tokenized (if it is a
  known raw value) or dropped, and if the summary cannot be made safe we fall
  back to keeping the un-summarized history (fail-closed) rather than persisting
  a corrupt summary.

Two hard invariants:

* **Vault counters are never rewound.** Validation and repair are *read-mostly*
  against the vault; re-tokenizing a leaked raw value may allocate a *new*
  placeholder (counters move forward only), but nothing ever resets a counter or
  re-points an existing placeholder. A compaction pass can only ever add, never
  renumber.
* **No raw value is persisted.** A summary that still contains a raw sensitive
  value after repair is rejected outright.

This module reasons purely over placeholder *tags* and the scoped vault; the
re-tokenize path delegates to the same :func:`sanitize_tool_output` the tool
boundary uses (imported at module scope so tests can patch it identically to the
rest of the privacy runtime).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from cloakbot.privacy.core.placeholders import PLACEHOLDER_RE
from cloakbot.privacy.core.sanitization.sanitize import sanitize_tool_output
from cloakbot.privacy.core.state.vault import _SessionMap, get_map


def extract_tokens(text: str) -> set[str]:
    """Return the set of distinct ``<<TAG_N>>`` placeholders present in *text*."""
    if not text:
        return set()
    return {m.group(0) for m in PLACEHOLDER_RE.finditer(text)}


def _vault_known(smap: _SessionMap, token: str) -> bool:
    """True when *token* is a placeholder this vault actually minted."""
    return (
        token in smap.placeholder_to_entity
        or token in smap.placeholder_to_original
        or token in smap.placeholder_to_computation
        or token in smap.placeholder_to_value
    )


def _counter_snapshot(smap: _SessionMap) -> dict[str, int]:
    """Snapshot the per-tag allocation counters (the rewind tripwire)."""
    return dict(smap.counters)


@dataclass(frozen=True)
class CompactionValidation:
    """Outcome of validating one summary against the scoped vault."""

    ok: bool
    summary: str
    foreign_tokens: frozenset[str] = field(default_factory=frozenset)
    renumbered_tokens: frozenset[str] = field(default_factory=frozenset)
    dropped: bool = False
    reason: str = ""


def validate_placeholders(
    summary: str,
    session_key: str,
    *,
    allowed_tokens: set[str],
) -> CompactionValidation:
    """Validate a post-summarize *summary* against the scoped vault.

    ``allowed_tokens`` is the set of placeholders present in the *pre-compaction*
    input window — the only tokens a faithful summary may legitimately carry.

    A token in the summary is rejected when it is:

    * **foreign** — not minted by this (scoped) vault at all (hallucinated), or
    * **renumbered** — minted by the vault but **not** a member of
      ``allowed_tokens`` (the model swapped one valid placeholder for another).

    Both rejection classes are treated identically downstream (the span is
    repaired or dropped); they are reported separately only for telemetry.
    This never mutates the vault and never rewinds a counter.
    """
    smap = get_map(session_key)
    summary_tokens = extract_tokens(summary)

    foreign: set[str] = set()
    renumbered: set[str] = set()
    for token in summary_tokens:
        if token in allowed_tokens:
            continue
        if _vault_known(smap, token):
            # Exists in the vault but was not in the input window — the model
            # substituted a different (valid-looking) placeholder. Forbidden:
            # restoration would resolve to the wrong entity.
            renumbered.add(token)
        else:
            foreign.add(token)

    ok = not foreign and not renumbered
    reason = ""
    if not ok:
        reason = "renumbered or foreign placeholder(s) in summary"
    return CompactionValidation(
        ok=ok,
        summary=summary,
        foreign_tokens=frozenset(foreign),
        renumbered_tokens=frozenset(renumbered),
        reason=reason,
    )


async def assert_tokenized(text: str, session_key: str) -> str:
    """Pre-summarize guard: return *text* guaranteed to be already tokenized.

    The compaction window should already be placeholdered (it is replayed
    session history that crossed the per-turn boundary). This is the
    sanitize-or-fail-closed backstop: we re-run the tool-output sanitizer, which
    pre-swaps known vault surfaces and tokenizes anything still raw, so the
    summarizer can never receive a raw sensitive value even if an upstream pass
    missed one. The sanitizer fails *closed* (raises) on detector unavailability;
    we propagate that so the consolidator's own ``try/except`` raw-archives the
    chunk rather than shipping raw text to the summarizer.
    """
    sanitized, _modified, _entities = await sanitize_tool_output(
        text,
        session_key,
    )
    return sanitized


@dataclass
class CompactionGuardResult:
    """Result of guarding one summarize round."""

    accepted: bool
    summary: str | None
    reason: str = ""


class CompactionGuard:
    """Stateful Cap D contract around one consolidation window.

    Lifecycle for one compaction round::

        guard = CompactionGuard(session_key)
        safe_input = await guard.prepare(window_text)   # pre-summarize
        summary = await stub_or_llm_summarize(safe_input)
        result = await guard.finalize(summary)          # post-summarize

    ``prepare`` records the allowed-token set (the placeholders in the
    *sanitized* input) and snapshots the vault counters. ``finalize`` validates
    the summary, repairs orphan/foreign/renumbered/raw spans, and fails closed
    (``accepted=False``) when the summary cannot be made safe — telling the
    caller to keep the un-summarized history. Counters are asserted never to have
    rewound across the round.
    """

    def __init__(self, session_key: str) -> None:
        self.session_key = session_key
        self._allowed_tokens: set[str] = set()
        self._counters_before: dict[str, int] = {}
        self._prepared = False

    async def prepare(self, window_text: str) -> str:
        """Pre-summarize: tokenize (fail-closed) and pin the allowed-token set."""
        smap = get_map(self.session_key)
        self._counters_before = _counter_snapshot(smap)
        safe_input = await assert_tokenized(window_text, self.session_key)
        self._allowed_tokens = extract_tokens(safe_input)
        self._prepared = True
        return safe_input

    async def finalize(self, summary: str | None) -> CompactionGuardResult:
        """Post-summarize: validate + repair the summary, fail closed if unsafe."""
        if not self._prepared:  # pragma: no cover - defensive
            raise RuntimeError("CompactionGuard.finalize called before prepare")
        if not summary:
            self._assert_counters_not_rewound()
            return CompactionGuardResult(accepted=True, summary=summary, reason="empty")

        validation = validate_placeholders(
            summary,
            self.session_key,
            allowed_tokens=self._allowed_tokens,
        )

        # Renumbering is UNREPAIRABLE: the model rewrote one valid placeholder as
        # a *different* valid placeholder, so restoration now resolves to the
        # wrong human/entity. We cannot recover which token it meant, so we fail
        # closed — keep the un-summarized history rather than persist a summary
        # that silently mis-attributes. (Counters are not touched.)
        if validation.renumbered_tokens:
            self._assert_counters_not_rewound()
            logger.bind(privacy="compaction").warning(
                "compaction: rejected summary with {} renumbered placeholder(s) "
                "(session={})",
                len(validation.renumbered_tokens),
                self.session_key,
            )
            return CompactionGuardResult(
                accepted=False,
                summary=None,
                reason="renumbered placeholder in summary",
            )

        # Foreign (hallucinated) tokens were never minted by this vault, so they
        # carry no attribution to corrupt — drop their spans and keep the rest.
        repaired = summary
        if validation.foreign_tokens:
            repaired = self._strip_bad_tokens(summary, validation.foreign_tokens)
            logger.bind(privacy="compaction").warning(
                "compaction: dropped {} foreign placeholder(s) from summary "
                "(session={})",
                len(validation.foreign_tokens),
                self.session_key,
            )

        # Re-tokenize any raw sensitive value the summarizer may have emitted.
        # This is the fail-closed backstop: a raw value in persisted-at-rest text
        # is the worst outcome, so we run it through the same sanitizer the tool
        # boundary uses. It may allocate a *new* placeholder (counters only move
        # forward), never rewinding or re-pointing an existing one.
        retokenized, _modified, _entities = await sanitize_tool_output(
            repaired,
            self.session_key,
        )

        self._assert_counters_not_rewound()

        # After repair the summary must contain only allowed tokens (plus any
        # freshly-minted ones from re-tokenizing a raw value). A foreign token
        # surviving the drop means repair failed: fail closed.
        post_tokens = extract_tokens(retokenized)
        smap = get_map(self.session_key)
        for token in post_tokens:
            if token in self._allowed_tokens:
                continue
            if _vault_known(smap, token):
                # Either an originally-allowed token or a freshly re-tokenized
                # raw value the vault now owns (counters moved forward). Both ok.
                continue
            return CompactionGuardResult(
                accepted=False,
                summary=None,
                reason="foreign placeholder survived repair",
            )

        return CompactionGuardResult(
            accepted=True,
            summary=retokenized,
            reason="repaired" if validation.foreign_tokens else "clean",
        )

    @staticmethod
    def _strip_bad_tokens(text: str, bad: frozenset[str] | set[str]) -> str:
        """Drop the spans of *bad* placeholders, collapsing surrounding space."""
        out = text
        for token in bad:
            out = out.replace(token, "")
        # Collapse the double-spaces / dangling separators a removal can leave.
        lines = [" ".join(line.split()) for line in out.splitlines()]
        return "\n".join(lines)

    def _assert_counters_not_rewound(self) -> None:
        """Tripwire: a compaction pass may grow counters, never shrink them."""
        smap = get_map(self.session_key)
        for tag, before in self._counters_before.items():
            after = smap.counters.get(tag, 0)
            if after < before:  # pragma: no cover - invariant guard
                raise RuntimeError(
                    f"compaction rewound vault counter for {tag!r}: "
                    f"{before} -> {after}"
                )


__all__ = [
    "CompactionGuard",
    "CompactionGuardResult",
    "CompactionValidation",
    "assert_tokenized",
    "extract_tokens",
    "validate_placeholders",
]
