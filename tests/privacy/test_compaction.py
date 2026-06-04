"""[Cap D] Placeholder-stable context compaction.

Plan acceptance test (docs/exec-plans/active/nanobot-rebase.md, row D):

  > a compaction-aware vault contract invoked at the autocompact/consolidation
  > boundary: pre-summarize asserts the text is already tokenized
  > (sanitize-or-fail-closed); post-summarize ``validate_placeholders(summary)``
  > confirms every ``<<TAG_N>>`` exists in the (scoped) vault, rejects foreign
  > tokens, and forbids renumbering by diffing the token set against
  > pre-compaction; orphan/foreign token -> re-tokenize or drop that span, keep
  > un-summarized history (fail-closed); vault counters never rewound.

  > Cap D acceptance test: stubbed summarizer that preserves / drops a token /
  > renumbers / emits a raw value -> first passes, others rejected/repaired;
  > counters unchanged.

The guard reuses the Cap B scoped-vault API (``get_map`` / ``VaultScope``) and the
same ``sanitize_tool_output`` the tool boundary uses for the re-tokenize backstop.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import cloakbot.privacy.compaction as compaction
import cloakbot.privacy.core.state.vault as vault
from cloakbot.privacy.compaction import (
    CompactionGuard,
    extract_tokens,
    validate_placeholders,
)
from cloakbot.privacy.compaction_provider import (
    CompactionGuardedProvider,
    install_compaction_guard,
)
from cloakbot.privacy.core.state.vault import get_map, set_vault_workspace
from cloakbot.providers.base import LLMResponse

SESSION = "compaction"


@pytest.fixture()
def real_vault(tmp_path: Path):
    """Point the vault at a real on-disk workspace and reset all caches."""
    set_vault_workspace(tmp_path)
    vault._cache.clear()
    vault._ephemeral_cache.clear()
    vault._routes().clear()
    yield tmp_path
    vault._cache.clear()
    vault._ephemeral_cache.clear()
    vault._routes().clear()


@pytest.fixture()
def seeded_vault(real_vault: Path):
    """Mint two stable placeholders the compaction window already references."""
    smap = get_map(SESSION)
    person, _ = smap.get_or_create_placeholder("Jane Doe", "PERSON", turn_id="t1")
    email, _ = smap.get_or_create_placeholder("jane@acme.com", "EMAIL", turn_id="t1")
    assert person == "<<PERSON_1>>"
    assert email == "<<EMAIL_1>>"
    return smap


def _window() -> str:
    return "User <<PERSON_1>> asked about the invoice for <<EMAIL_1>>."


# --------------------------------------------------------------------------- #
# extract_tokens / validate_placeholders units
# --------------------------------------------------------------------------- #


def test_extract_tokens_picks_up_every_placeholder() -> None:
    text = "a <<PERSON_1>> b <<EMAIL_1>> c <<PERSON_1>>"
    assert extract_tokens(text) == {"<<PERSON_1>>", "<<EMAIL_1>>"}


def test_extract_tokens_empty() -> None:
    assert extract_tokens("no tokens here") == set()


def test_validate_accepts_preserved_tokens(seeded_vault) -> None:
    allowed = {"<<PERSON_1>>", "<<EMAIL_1>>"}
    result = validate_placeholders(
        "Summary: <<PERSON_1>> emailed <<EMAIL_1>>.",
        SESSION,
        allowed_tokens=allowed,
    )
    assert result.ok
    assert not result.foreign_tokens
    assert not result.renumbered_tokens


def test_validate_accepts_subset_of_allowed(seeded_vault) -> None:
    """Dropping a token (using fewer than allowed) is faithful, not a violation."""
    result = validate_placeholders(
        "Summary mentions only <<PERSON_1>>.",
        SESSION,
        allowed_tokens={"<<PERSON_1>>", "<<EMAIL_1>>"},
    )
    assert result.ok


def test_validate_flags_foreign_token(seeded_vault) -> None:
    """A placeholder the vault never minted is foreign (hallucinated)."""
    result = validate_placeholders(
        "Summary: <<PERSON_1>> and <<SSN_9>>.",
        SESSION,
        allowed_tokens={"<<PERSON_1>>", "<<EMAIL_1>>"},
    )
    assert not result.ok
    assert result.foreign_tokens == frozenset({"<<SSN_9>>"})


def test_validate_flags_renumbered_token(seeded_vault) -> None:
    """A vault-known token that was NOT in the window is a renumber."""
    # Mint a third placeholder that exists in the vault but isn't in this window.
    seeded_vault.get_or_create_placeholder("Acme Corp", "ORG", turn_id="t1")
    result = validate_placeholders(
        "Summary swapped in <<ORG_1>> for the person.",
        SESSION,
        allowed_tokens={"<<PERSON_1>>", "<<EMAIL_1>>"},
    )
    assert not result.ok
    assert result.renumbered_tokens == frozenset({"<<ORG_1>>"})


# --------------------------------------------------------------------------- #
# CompactionGuard — the four plan cases
# --------------------------------------------------------------------------- #


async def test_guard_preserves_clean_summary(seeded_vault) -> None:
    """Case 1: summarizer preserves the tokens -> accepted unchanged."""
    guard = CompactionGuard(SESSION)
    counters_before = dict(seeded_vault.counters)

    await guard.prepare(_window())
    result = await guard.finalize("<<PERSON_1>> asked about <<EMAIL_1>>.")

    assert result.accepted
    assert result.summary == "<<PERSON_1>> asked about <<EMAIL_1>>."
    assert seeded_vault.counters == counters_before  # never rewound, never grew


async def test_guard_repairs_foreign_token_by_dropping(seeded_vault) -> None:
    """Case 2 (drop): a foreign token is stripped; the rest survives, accepted."""
    guard = CompactionGuard(SESSION)
    counters_before = dict(seeded_vault.counters)

    await guard.prepare(_window())
    result = await guard.finalize("<<PERSON_1>> and a stray <<SSN_7>> token.")

    assert result.accepted
    assert "<<SSN_7>>" not in (result.summary or "")
    assert "<<PERSON_1>>" in (result.summary or "")
    assert seeded_vault.counters == counters_before


async def test_guard_rejects_renumbered_summary(seeded_vault) -> None:
    """Case 3 (renumber): a known-but-different token fails closed (no persist)."""
    seeded_vault.get_or_create_placeholder("Acme Corp", "ORG", turn_id="t1")
    counters_after_org = dict(seeded_vault.counters)

    guard = CompactionGuard(SESSION)
    await guard.prepare(_window())
    # Model renumbered: swapped the person/email for an unrelated org token.
    result = await guard.finalize("Summary refers to <<ORG_1>> instead.")

    assert not result.accepted
    assert result.summary is None
    assert "renumber" in result.reason
    # Counters never rewound by the rejected pass.
    assert seeded_vault.counters == counters_after_org


async def test_guard_retokenizes_raw_value(seeded_vault, monkeypatch) -> None:
    """Case 4 (raw value): a leaked raw value is re-tokenized, not persisted raw.

    The autouse fixture makes ``sanitize_tool_output`` a transparent no-op, so we
    patch the compaction module's reference to a stub that mints a placeholder for
    the raw value (mirroring the real detector). The guard must (a) never persist
    the raw value, (b) only move counters forward.
    """

    async def _tokenizing_sanitize(text, session_key, **kwargs):
        smap = get_map(session_key)
        if "555-12-9999" in text:
            ph, _ = smap.get_or_create_placeholder("555-12-9999", "SSN")
            return text.replace("555-12-9999", ph), True, []
        return text, False, []

    monkeypatch.setattr(compaction, "sanitize_tool_output", _tokenizing_sanitize)

    guard = CompactionGuard(SESSION)
    ssn_counter_before = seeded_vault.counters.get("SSN", 0)

    await guard.prepare(_window())
    result = await guard.finalize("<<PERSON_1>> SSN is 555-12-9999 per the record.")

    assert result.accepted
    assert "555-12-9999" not in (result.summary or "")  # raw never persisted
    assert "<<SSN_1>>" in (result.summary or "")
    # Counter only moved forward (a new placeholder was minted), never rewound.
    assert seeded_vault.counters.get("SSN", 0) == ssn_counter_before + 1


async def test_guard_counters_never_rewound_across_all_cases(seeded_vault) -> None:
    """The vault counters are monotonic across a clean + a rejected pass."""
    before = dict(seeded_vault.counters)

    g1 = CompactionGuard(SESSION)
    await g1.prepare(_window())
    await g1.finalize("<<PERSON_1>> only.")

    g2 = CompactionGuard(SESSION)
    await g2.prepare(_window())
    await g2.finalize("<<EMAIL_1>> and a foreign <<PHONE_5>>.")

    after = get_map(SESSION).counters
    for tag, count in before.items():
        assert after.get(tag, 0) >= count


# --------------------------------------------------------------------------- #
# CompactionGuardedProvider — the additive consolidation-boundary wiring
# --------------------------------------------------------------------------- #


async def test_guarded_provider_passes_clean_summary(seeded_vault) -> None:
    inner = MagicMock()
    inner.chat_with_retry = AsyncMock(
        return_value=LLMResponse(content="<<PERSON_1>> emailed <<EMAIL_1>>.", finish_reason="stop")
    )
    provider = CompactionGuardedProvider(inner, session_key=SESSION)

    messages = [
        {"role": "system", "content": "summarize"},
        {"role": "user", "content": _window()},
    ]
    resp = await provider.chat_with_retry(messages)

    assert resp.finish_reason == "stop"
    assert resp.content == "<<PERSON_1>> emailed <<EMAIL_1>>."


async def test_guarded_provider_fails_closed_on_renumber(seeded_vault) -> None:
    """A renumbered summary -> finish_reason=error so archive() raw-archives."""
    seeded_vault.get_or_create_placeholder("Acme Corp", "ORG", turn_id="t1")
    inner = MagicMock()
    inner.chat_with_retry = AsyncMock(
        return_value=LLMResponse(content="Refers to <<ORG_1>> instead.", finish_reason="stop")
    )
    provider = CompactionGuardedProvider(inner, session_key=SESSION)

    messages = [{"role": "user", "content": _window()}]
    resp = await provider.chat_with_retry(messages)

    assert resp.finish_reason == "error"
    assert "rejected" in (resp.content or "")


async def test_guarded_provider_delegates_unknown_attrs() -> None:
    inner = MagicMock()
    inner.generation = MagicMock(max_tokens=4096)
    provider = CompactionGuardedProvider(inner)
    assert provider.generation.max_tokens == 4096


def test_install_compaction_guard_is_idempotent() -> None:
    consolidator = MagicMock()
    inner = MagicMock()
    consolidator.provider = inner

    install_compaction_guard(consolidator)
    assert isinstance(consolidator.provider, CompactionGuardedProvider)
    first = consolidator.provider

    install_compaction_guard(consolidator)
    assert consolidator.provider is first  # no double-wrap


# --------------------------------------------------------------------------- #
# End-to-end through the real Consolidator (no fork — additive wrapper only)
# --------------------------------------------------------------------------- #


async def test_consolidator_keeps_unsummarized_history_on_reject(seeded_vault, tmp_path) -> None:
    """Wiring the guard onto a real Consolidator: a renumbered summary -> raw archive.

    Proves the fail-closed contract end-to-end: the corrupt summary is NOT
    persisted; the un-summarized window is raw-archived instead.
    """
    from cloakbot.agent.memory import Consolidator, MemoryStore

    seeded_vault.get_or_create_placeholder("Acme Corp", "ORG", turn_id="t1")

    store = MemoryStore(tmp_path)
    inner = MagicMock()
    inner.chat_with_retry = AsyncMock(
        return_value=LLMResponse(content="Now about <<ORG_1>>.", finish_reason="stop")
    )
    sessions = MagicMock()
    sessions.save = MagicMock()
    consolidator = Consolidator(
        store=store,
        provider=inner,
        model="m",
        sessions=sessions,
        context_window_tokens=1000,
        build_messages=MagicMock(return_value=[]),
        get_tool_definitions=MagicMock(return_value=[]),
        max_completion_tokens=100,
    )
    # Point the consolidation summary at our seeded vault session.
    install_compaction_guard(consolidator)
    consolidator.provider._session_key = SESSION

    messages = [
        {"role": "user", "content": "<<PERSON_1>> wanted <<EMAIL_1>>.", "timestamp": "2026-06-04 10:00"},
    ]
    summary = await consolidator.archive(messages)

    # Rejected summary -> archive() returns None (raw-dump fallback).
    assert summary is None
    entries = store.read_unprocessed_history(since_cursor=0)
    assert len(entries) == 1
    assert "[RAW]" in entries[0]["content"]
    # The corrupt <<ORG_1>> summary was never persisted.
    assert "<<ORG_1>>" not in entries[0]["content"]
