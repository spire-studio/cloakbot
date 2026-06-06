"""Cap A — StreamingSanitizer carry-over window acceptance + fuzz tests.

The streaming sanitizer must guarantee that a detectable entity straddling any
poll boundary is detected as one unit and tokenized once — never partially
emitted as raw characters across the seam.

Per conftest's ``_transparent_local_detector`` fixture, redaction tests supply
their own detector. :class:`StreamingSanitizer` takes an injected ``sanitize_fn``
so each test passes a deterministic stub directly (the production default is
``sanitize_tool_output``).
"""

from __future__ import annotations

import asyncio

import pytest

from cloakbot.privacy.core.types import GeneralEntity
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.runtime.streaming_sanitizer import (
    DEFAULT_CARRY_OVER_CHARS,
    StreamingSanitizer,
    StreamingSanitizerRegistry,
)
from cloakbot.privacy.runtime.tool_interceptor import ToolPrivacyInterceptor
from cloakbot.providers.base import ToolCallRequest
from cloakbot.tool_privacy import ToolPrivacyClass

# A HIGH-severity-shaped fixed entity. Single stable placeholder so we can assert
# "tokenized once, reused" and "the raw value never appears in emitted output".
ENTITY = "999-77-1234-SSN-MARKER"
PLACEHOLDER = "<<IDENTIFIER_1>>"


def _stub_sanitize_fn(entity: str = ENTITY, placeholder: str = PLACEHOLDER):
    """Deterministic detector: replace every full ``entity`` with ``placeholder``.

    Deterministic over any prefix (no vault state needed) so the streaming
    sanitizer's re-detection invariant holds exactly.
    """

    async def _fn(text: str, _session_key: str, *, turn_id: str | None = None):
        out = text.replace(entity, placeholder)
        entities = (
            [GeneralEntity(text=entity, entity_type="identifier")] if entity in text else []
        )
        return out, entity in text, entities

    return _fn


async def _drain(sanitizer: StreamingSanitizer, chunks: list[str]) -> str:
    out = ""
    for chunk in chunks:
        out += await sanitizer.feed(chunk)
    out += await sanitizer.finalize()
    return out


@pytest.mark.asyncio
async def test_entity_straddling_poll_boundary_emits_zero_raw_chars() -> None:
    """Cap A acceptance: a HIGH entity split across a 4096-byte poll boundary
    is tokenized whole, never emitted raw, and the placeholder is reused."""
    boundary = 4096
    # Place the entity so it spans exactly across the 4096-byte boundary.
    half = len(ENTITY) // 2
    poll_1 = ("a" * (boundary - half)) + ENTITY[:half]
    poll_2 = ENTITY[half:] + ("b" * 100) + ENTITY + ("c" * 100)

    sanitizer = StreamingSanitizer("cli:test", "exec:s1", sanitize_fn=_stub_sanitize_fn())
    emitted = await _drain(sanitizer, [poll_1, poll_2])

    # Zero raw chars of the entity survive across the seam.
    assert ENTITY not in emitted
    # The straddling entity AND the later in-poll entity both became the same
    # reused placeholder.
    assert emitted.count(PLACEHOLDER) == 2
    # Structure is preserved (filler stays intact, in order).
    assert emitted.startswith("a" * (boundary - half))
    assert emitted == (
        ("a" * (boundary - half)) + PLACEHOLDER + ("b" * 100) + PLACEHOLDER + ("c" * 100)
    )
    assert sanitizer.modified is True


@pytest.mark.asyncio
async def test_carry_over_window_covers_longest_entity_span() -> None:
    """The default carry-over window is >= the longest detectable entity span
    (~256 chars), so an entity can never span more than one window boundary."""
    assert DEFAULT_CARRY_OVER_CHARS >= 256
    assert len(ENTITY) <= DEFAULT_CARRY_OVER_CHARS


@pytest.mark.asyncio
async def test_finalize_flushes_residual_tail() -> None:
    """An entity sitting entirely inside the trailing carry-over window is held
    back from feed() and flushed (sanitized) only on finalize()."""
    sanitizer = StreamingSanitizer("cli:test", "exec:s1", sanitize_fn=_stub_sanitize_fn())
    # Whole stream shorter than the window -> feed() emits nothing.
    text = "prefix " + ENTITY
    assert await sanitizer.feed(text) == ""
    flushed = await sanitizer.finalize()
    assert flushed == "prefix " + PLACEHOLDER
    assert ENTITY not in flushed


@pytest.mark.asyncio
async def test_finalize_is_idempotent_and_blocks_further_feeds() -> None:
    sanitizer = StreamingSanitizer("cli:test", "exec:s1", sanitize_fn=_stub_sanitize_fn())
    await sanitizer.feed("hello world " + ("x" * 1000) + ENTITY)
    first = await sanitizer.finalize()
    assert ENTITY not in first
    assert await sanitizer.finalize() == ""
    with pytest.raises(RuntimeError):
        await sanitizer.feed("more")


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [4096])
async def test_fuzz_entity_at_every_byte_offset_of_12kb_stream(chunk_size: int) -> None:
    """Cap A fuzz: slide a fixed entity across EVERY byte offset of a 12KB stream
    chunked at 4096 bytes. Zero seam leaks at any offset."""
    stream_len = 12 * 1024
    entity = ENTITY
    placeholder = PLACEHOLDER
    fn = _stub_sanitize_fn(entity, placeholder)

    async def run_one(offset: int) -> None:
        # Build a 12KB stream with the entity embedded starting at ``offset``
        # (overwriting filler, so total length stays exactly ``stream_len``).
        raw = ("." * offset) + entity + ("." * (stream_len - offset - len(entity)))
        assert len(raw) == stream_len
        # Chunk the raw stream into fixed 4096-byte polls.
        chunks = [raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)]
        sanitizer = StreamingSanitizer("cli:test", f"exec:{offset}", sanitize_fn=fn)
        emitted = await _drain(sanitizer, chunks)
        # Seam-leak invariant: the raw entity NEVER appears in emitted output.
        assert entity not in emitted, f"seam leak at offset {offset}"
        # The entity (present exactly once in the raw stream) is tokenized once.
        assert emitted.count(placeholder) == 1, f"placeholder count at offset {offset}"
        # Emitted output, with the placeholder mapped back, reconstructs the raw
        # stream exactly (no dropped or duplicated bytes at the seam).
        assert emitted.replace(placeholder, entity) == raw

    # Slide across every offset where the entity fits fully inside the 12KB
    # stream — this includes all 4096 multiples and the bytes immediately
    # around them, i.e. every poll boundary.
    offsets = range(0, stream_len - len(entity) + 1)
    await asyncio.gather(*(run_one(o) for o in offsets))


@pytest.mark.asyncio
async def test_registry_shares_carry_over_across_polls_same_stream() -> None:
    """The registry keys carry-over by (session_key, stream_id) so successive
    polls of one exec session share window state."""
    registry = StreamingSanitizerRegistry(sanitize_fn=_stub_sanitize_fn())
    half = len(ENTITY) // 2
    poll_1 = ("a" * 5000) + ENTITY[:half]
    poll_2 = ENTITY[half:] + ("b" * 5000)

    s1 = registry.get("cli:test", "exec:S")
    out = await s1.feed(poll_1)
    s2 = registry.get("cli:test", "exec:S")
    assert s2 is s1  # same stream -> same sanitizer instance
    out += await s2.feed(poll_2)
    out += await registry.finalize_stream("cli:test", "exec:S")

    assert ENTITY not in out
    assert out.count(PLACEHOLDER) == 1
    assert not registry.has("cli:test", "exec:S")  # finalize drops the stream


@pytest.mark.asyncio
async def test_distinct_streams_do_not_share_carry_over() -> None:
    registry = StreamingSanitizerRegistry(sanitize_fn=_stub_sanitize_fn())
    a = registry.get("cli:test", "exec:A")
    b = registry.get("cli:test", "exec:B")
    assert a is not b


@pytest.mark.asyncio
async def test_interceptor_routes_streaming_tool_through_carry_over_window() -> None:
    """End-to-end through ToolPrivacyInterceptor: an entity split across two
    write_stdin polls of the same exec session never leaks raw to the model."""
    from unittest.mock import patch

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="run it")
    interceptor = ToolPrivacyInterceptor(ctx)

    half = len(ENTITY) // 2
    # poll_1's process output ends mid-entity; its status trailer is stripped off
    # before the output is fed to the carry-over window. poll_2's output begins
    # with the rest of the entity, so the two output regions concatenate to the
    # whole entity and it is tokenized once.
    poll_1 = ("log line\n" * 600) + ENTITY[:half] + "\nProcess running. session_id: S1\nElapsed: 1.0s"
    poll_2 = ENTITY[half:] + " done\nExit code: 0\nElapsed: 2.0s"

    call_1 = ToolCallRequest(id="c1", name="write_stdin", arguments={"session_id": "S1"})
    call_2 = ToolCallRequest(id="c2", name="write_stdin", arguments={"session_id": "S1"})

    with patch(
        "cloakbot.privacy.runtime.streaming_sanitizer.sanitize_tool_output",
        new=_stub_sanitize_fn(),
    ):
        out_1 = await interceptor.sanitize_tool_result(
            call_1, poll_1, privacy_class=ToolPrivacyClass.SIDE_EFFECT
        )
        out_2 = await interceptor.sanitize_tool_result(
            call_2, poll_2, privacy_class=ToolPrivacyClass.SIDE_EFFECT
        )

    combined = out_1 + out_2
    assert ENTITY not in out_1
    assert ENTITY not in out_2
    assert ENTITY not in combined
    assert PLACEHOLDER in combined
    # Two poll records, both flagged sanitized.
    assert [r.tool_name for r in ctx.tool_results] == ["write_stdin", "write_stdin"]
    assert ctx.tool_results[1].was_sanitized is True


@pytest.mark.asyncio
async def test_interceptor_exec_to_write_stdin_boundary_does_not_split_entity() -> None:
    """M1: an entity straddling the exec-poll -> first-write_stdin boundary is
    NOT split.

    The initiating ``exec`` call has no ``session_id`` argument — the id is
    minted server-side and only printed in the result ("Process running.
    session_id: S1"). The continuation ``write_stdin`` carries ``session_id=S1``
    in its args. Before the fix the exec poll keyed on its call id
    (``exec:c1``) while write_stdin keyed on ``write_stdin:S1`` — two separate
    StreamingSanitizers — so an entity split across that boundary leaked raw.
    Now both converge on ``exec_session:S1`` and share the held tail.
    """
    from unittest.mock import patch

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="run it")
    interceptor = ToolPrivacyInterceptor(ctx)

    half = len(ENTITY) // 2
    # exec poll: process still running, output ends mid-entity; the session_id
    # only appears in the trailer (the exec call args have none).
    exec_poll = (
        ("log line\n" * 600)
        + ENTITY[:half]
        + "\nProcess running. session_id: S1\nElapsed: 1.0s"
    )
    # write_stdin continuation: output begins with the rest of the entity.
    write_poll = ENTITY[half:] + " done\nExit code: 0\nElapsed: 2.0s"

    exec_call = ToolCallRequest(id="c1", name="exec", arguments={"command": "run"})
    write_call = ToolCallRequest(id="c2", name="write_stdin", arguments={"session_id": "S1"})

    with patch(
        "cloakbot.privacy.runtime.streaming_sanitizer.sanitize_tool_output",
        new=_stub_sanitize_fn(),
    ):
        out_exec = await interceptor.sanitize_tool_result(
            exec_call, exec_poll, privacy_class=ToolPrivacyClass.SIDE_EFFECT
        )
        out_write = await interceptor.sanitize_tool_result(
            write_call, write_poll, privacy_class=ToolPrivacyClass.SIDE_EFFECT
        )

    combined = out_exec + out_write
    # No raw half of the entity leaks from either poll, nor across the seam.
    assert ENTITY not in out_exec
    assert ENTITY[:half] not in out_exec  # the half-entity tail was HELD, not emitted raw
    assert ENTITY not in out_write
    assert ENTITY not in combined
    # The straddling entity is tokenized exactly once, whole.
    assert PLACEHOLDER in combined
    assert combined.count(PLACEHOLDER) == 1
    # The exec poll's status trailer is still present (re-appended verbatim).
    assert "Process running. session_id: S1" in out_exec


@pytest.mark.asyncio
async def test_interceptor_streaming_without_session_id_falls_back_safely() -> None:
    """A streaming tool call with no stable stream key still never leaks raw."""
    from unittest.mock import patch

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="x")
    interceptor = ToolPrivacyInterceptor(ctx)
    call = ToolCallRequest(id="c1", name="long_task", arguments={})

    with patch(
        "cloakbot.privacy.runtime.streaming_sanitizer.sanitize_tool_output",
        new=_stub_sanitize_fn(),
    ):
        out = await interceptor.sanitize_tool_result(
            call, f"objective contains {ENTITY} secret", privacy_class=ToolPrivacyClass.SIDE_EFFECT
        )

    assert ENTITY not in out
    assert PLACEHOLDER in out


@pytest.mark.asyncio
async def test_interceptor_exec_running_poll_holds_tail_for_continuation() -> None:
    """[M1] An ``exec`` poll that prints "Process running" HOLDS its carry-over
    tail for the continuation, which now arrives under the SAME canonical
    ``exec_session:{id}`` stream key as a ``write_stdin`` poll.

    Previously the live exec poll flushed per-call (its continuation was a
    separately-keyed ``write_stdin`` stream), which is exactly what let an entity
    straddling the boundary split. Now the exec tail is withheld and inherited by
    the first ``write_stdin`` continuation; the held output never leaks raw and
    flushes on the next same-session poll. The status trailer is always emitted."""
    from unittest.mock import patch

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="run")
    interceptor = ToolPrivacyInterceptor(ctx)
    exec_call = ToolCallRequest(id="c1", name="exec", arguments={"command": "tail -f log"})
    # exec started a yielding session; trailer says Process running. The short
    # output sits inside the carry-over window, so it is HELD for the continuation.
    exec_result = f"started {ENTITY} ok\nProcess running. session_id: S1\nElapsed: 1.0s"
    # The continuation poll completes the session and flushes the held output.
    write_call = ToolCallRequest(id="c2", name="write_stdin", arguments={"session_id": "S1"})
    write_result = "tail done\nExit code: 0\nElapsed: 2.0s"

    with patch(
        "cloakbot.privacy.runtime.streaming_sanitizer.sanitize_tool_output",
        new=_stub_sanitize_fn(),
    ):
        out_exec = await interceptor.sanitize_tool_result(
            exec_call, exec_result, privacy_class=ToolPrivacyClass.SIDE_EFFECT
        )
        out_write = await interceptor.sanitize_tool_result(
            write_call, write_result, privacy_class=ToolPrivacyClass.SIDE_EFFECT
        )

    # The live exec poll withheld its output (held tail) but always emits the
    # status trailer so the model knows the process is still running.
    assert ENTITY not in out_exec
    assert "Process running. session_id: S1" in out_exec
    # The continuation flushes the held output, tokenized exactly once.
    combined = out_exec + out_write
    assert ENTITY not in combined
    assert combined.count(PLACEHOLDER) == 1
    assert "Exit code: 0" in out_write


@pytest.mark.asyncio
async def test_interceptor_write_stdin_running_poll_holds_tail_until_done() -> None:
    """A still-running ``write_stdin`` poll holds back its carry-over tail; the
    next same-session poll completes a boundary-straddling entity safely."""
    from unittest.mock import patch

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="run")
    interceptor = ToolPrivacyInterceptor(ctx)
    half = len(ENTITY) // 2
    poll_1 = ("x" * 4000) + ENTITY[:half] + "\nProcess running. session_id: S1\nElapsed: 1.0s"
    poll_2 = ENTITY[half:] + " end\nExit code: 0\nElapsed: 2.0s"
    c1 = ToolCallRequest(id="a", name="write_stdin", arguments={"session_id": "S1"})
    c2 = ToolCallRequest(id="b", name="write_stdin", arguments={"session_id": "S1"})

    with patch(
        "cloakbot.privacy.runtime.streaming_sanitizer.sanitize_tool_output",
        new=_stub_sanitize_fn(),
    ):
        out1 = await interceptor.sanitize_tool_result(c1, poll_1, privacy_class=ToolPrivacyClass.SIDE_EFFECT)
        out2 = await interceptor.sanitize_tool_result(c2, poll_2, privacy_class=ToolPrivacyClass.SIDE_EFFECT)

    # poll_1 withheld the partial entity (held in carry-over), so it never
    # appears raw; poll_2 completes and tokenizes it once.
    assert ENTITY not in out1
    assert ENTITY not in out2
    assert ENTITY[:half] not in out1  # partial held back, not emitted raw
    assert (out1 + out2).count(PLACEHOLDER) == 1
