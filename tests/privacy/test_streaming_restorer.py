"""Streaming output restorer (Cap A inverse).

Core invariant: for any way the stream is chopped into chunks, concatenating
every ``feed()`` output plus ``finalize()`` equals ``restore_tokens(full)`` — so
a ``<<TAG_N>>`` token split across chunks never leaks raw, and the streamed text
matches the final message / annotation offsets byte-for-byte.
"""

from __future__ import annotations

import pytest

from cloakbot.privacy.core.sanitization.restorer import restore_tokens
from cloakbot.privacy.core.state import vault
from cloakbot.privacy.runtime.streaming_restorer import StreamingRestorer


@pytest.fixture
def session(tmp_path):
    vault.set_vault_workspace(tmp_path)
    key = "webui:test"
    smap = vault.get_map(key)
    for original, tag in [
        ("Alice Chen", "PERSON"),
        ("alice@acme.com", "EMAIL"),
        ("TargetCorp", "ORG"),
    ]:
        smap.get_or_create_placeholder(original, tag, turn_id="t1")
    vault.save_map(key, smap)
    yield key
    vault._cache.clear()


def _drive(key: str, chunks: list[str]) -> str:
    r = StreamingRestorer(key)
    out = "".join(r.feed(c) for c in chunks)
    return out + r.finalize()


def test_single_chunk_complete_tokens(session):
    assert _drive(session, ["Hi <<PERSON_1>> at <<EMAIL_1>>."]) == "Hi Alice Chen at alice@acme.com."


def test_the_reported_bug_scenario(session):
    # Round 2 of the repro: "Your name is <<PERSON_1>>." must render restored.
    assert _drive(session, ["Your name is <<PERSON_1>>."]) == "Your name is Alice Chen."


def test_token_split_across_chunks_no_leak(session):
    out = _drive(session, ["Hi <<PER", "SON_1>> there"])
    assert out == "Hi Alice Chen there"
    assert "<<" not in out and "PERSON_1" not in out


def test_char_by_char_equals_whole(session):
    full = "Your name is <<PERSON_1>>, email <<EMAIL_1>>, org <<ORG_1>>!"
    expected = restore_tokens(full, vault.get_map(session))
    assert _drive(session, list(full)) == expected


@pytest.mark.parametrize("split", range(1, 45))
def test_every_split_point_equals_whole(session, split):
    full = "X <<PERSON_1>> Y <<EMAIL_1>> Z <<ORG_1>> end"
    expected = restore_tokens(full, vault.get_map(session))
    assert _drive(session, [full[:split], full[split:]]) == expected


def test_finalize_flushes_partial(session):
    r = StreamingRestorer(session)
    assert r.feed("name <<PER") == "name "  # partial token held back
    assert r.finalize() == "<<PER"  # incomplete -> flushed raw (not a real token)


def test_passthrough_when_no_placeholders(tmp_path):
    vault.set_vault_workspace(tmp_path)
    r = StreamingRestorer("webui:empty")
    # Empty vault -> straight passthrough, no buffering even with a lone '<'.
    assert r.feed("a < b plain") == "a < b plain"
    assert r.finalize() == ""
    vault._cache.clear()


def test_literal_double_angle_not_corrupted(session):
    # A non-token "<<" (e.g. a shift operator) survives intact across any split.
    full = "cout << x << y;"
    expected = restore_tokens(full, vault.get_map(session))
    assert expected == full  # nothing to restore
    for split in range(1, len(full)):
        assert _drive(session, [full[:split], full[split:]]) == full
