"""Stateful streaming sanitizer with a carry-over window (Cap A).

Streaming / poll tools (``exec``/``write_stdin`` exec sessions, shell, and
``long_task`` progress) hand the model their output **incrementally** — each
poll returns the bytes produced since the last poll. Sanitizing each poll's
text in isolation is unsafe: a single detectable entity (an SSN, an email, a
person's name) can straddle a poll boundary, so the local PII detector sees
only half of it on either side and emits **raw** characters to the remote model.

:class:`StreamingSanitizer` removes that seam. It buffers a tail "carry-over"
window at least as long as the longest detectable entity span, and only ever
emits sanitized output for the region of the stream that is far enough behind
the live end that **no future byte can extend an entity into it**. The held-back
tail is re-fed (prepended) on the next poll so every entity is detected as a
contiguous unit and gets one stable placeholder. ``finalize`` flushes whatever
tail remains.

Keying: one sanitizer instance per ``(session_key, stream_id)`` where
``stream_id`` is the tool-call id (or exec-session id). Held in a process-local
registry so successive polls of the same stream share carry-over state.

The detector is injected (defaults to :func:`sanitize_tool_output`) so tests can
patch a transparent or deterministic stub exactly like the rest of the privacy
runtime. The sanitizer relies on the detector being **deterministic for a given
prefix** — re-sanitizing a prefix of the raw stream must produce the same
placeholders. This holds because the session Vault reuses placeholders for known
surface forms (``replace_known_originals`` + ``get_or_create_placeholder``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from cloakbot.privacy.core.sanitization.sanitize import sanitize_tool_output
from cloakbot.privacy.core.types import DetectedEntity

# Carry-over window. Must be >= the longest detectable entity span so an entity
# can never span more than one window boundary. The chunker's structural overlap
# is 300 chars; 256 comfortably covers every entity family the local detector
# emits (emails, SSNs, names, addresses, ids) while keeping re-detection cheap.
DEFAULT_CARRY_OVER_CHARS = 256

# Detector signature: ``(text, session_key, *, turn_id) ->
# (sanitized, modified, entities)``. Matches ``sanitize_tool_output``.
SanitizeFn = Callable[..., Awaitable[tuple[str, bool, list[DetectedEntity]]]]


class StreamingSanitizer:
    """Sanitize an incrementally-produced text stream with zero seam leaks.

    Usage::

        s = StreamingSanitizer(session_key, stream_id)
        out1 = await s.feed(poll_1_text)   # emits only the settled prefix
        out2 = await s.feed(poll_2_text)
        tail = await s.finalize()          # flushes the residual window

    Each call returns the **newly settled** sanitized text (possibly empty when
    the whole poll still sits inside the carry-over window). Concatenating every
    return value (feeds + finalize) yields the fully-sanitized stream with each
    entity tokenized exactly once.
    """

    def __init__(
        self,
        session_key: str,
        stream_id: str,
        *,
        turn_id: str | None = None,
        carry_over_chars: int = DEFAULT_CARRY_OVER_CHARS,
        sanitize_fn: SanitizeFn | None = None,
    ) -> None:
        self.session_key = session_key
        self.stream_id = stream_id
        self._turn_id = turn_id
        self._carry_over = max(1, carry_over_chars)
        self._sanitize = sanitize_fn or sanitize_tool_output
        # The entire raw stream observed so far. The detector re-reads a prefix
        # of this each round; re-detection is deterministic via the Vault.
        self._raw = ""
        # How many chars of the *sanitized* whole-stream output we have already
        # emitted. We never re-emit a settled prefix.
        self._emitted_sanitized = 0
        # Aggregate signal: did any poll modify (tokenize) the stream?
        self._modified = False
        self._finalized = False
        # Entities observed across the whole stream (deduped on identity by the
        # caller's vault; we keep the running list for transparency records).
        self._entities: list[DetectedEntity] = []

    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def entities(self) -> list[DetectedEntity]:
        return list(self._entities)

    async def feed(self, text: str) -> str:
        """Append *text*, return any newly-settled sanitized output.

        Output within ``carry_over`` chars of the live tail is withheld until a
        later feed or :meth:`finalize`, so an entity that has not fully arrived —
        or one that straddles the settle boundary — is never partially emitted.
        """
        if self._finalized:
            raise RuntimeError("StreamingSanitizer.feed called after finalize")
        if not text:
            return ""
        self._raw += text
        return await self._emit(final=False)

    async def finalize(self) -> str:
        """Flush and sanitize the residual carry-over tail.

        Idempotent after the first call (returns ``""`` on repeat).
        """
        if self._finalized:
            return ""
        self._finalized = True
        return await self._emit(final=True)

    async def _emit(self, *, final: bool) -> str:
        """Emit newly-settled sanitized output.

        Correctness rests on a *double sanitization* check rather than trusting a
        raw offset. We sanitize the whole raw buffer, and (on a non-final feed)
        also sanitize ``raw[:-window]``. The settled output is the **longest
        common prefix** of those two sanitizations:

        - An entity wholly inside ``raw[:-window]`` tokenizes identically in both,
          so it falls inside the common prefix and is safely emitted.
        - An entity that straddles the ``-window`` boundary appears tokenized in
          the full sanitization but raw (or differently split) in the prefix one,
          so the common prefix stops *before* it — it is withheld until the next
          feed completes it.

        Because entities are at most ``window`` chars long, anything that could
        still grow is within ``window`` of the live tail, so the common prefix is
        always safe to emit. On ``final`` we emit the whole sanitization.
        """
        sanitized_full, modified, entities = await self._sanitize(
            self._raw,
            self.session_key,
            turn_id=self._turn_id,
        )
        self._modified = self._modified or modified
        # ``entities`` is recomputed over the whole buffer each pass, so we
        # snapshot the latest full list rather than appending (avoids duplicates).
        self._entities = list(entities)

        if final:
            safe_len = len(sanitized_full)
        elif len(self._raw) <= self._carry_over:
            # The entire buffer is still inside the carry-over window.
            safe_len = 0
        else:
            prefix_raw = self._raw[: len(self._raw) - self._carry_over]
            sanitized_prefix, _m, _e = await self._sanitize(
                prefix_raw,
                self.session_key,
                turn_id=self._turn_id,
            )
            safe_len = _common_prefix_len(sanitized_full, sanitized_prefix)

        if safe_len <= self._emitted_sanitized:
            return ""
        delta = sanitized_full[self._emitted_sanitized : safe_len]
        self._emitted_sanitized = safe_len
        return delta


def _common_prefix_len(a: str, b: str) -> int:
    """Length of the longest common prefix of *a* and *b*."""
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return i


class StreamingSanitizerRegistry:
    """Process-local registry of live :class:`StreamingSanitizer` instances.

    Keyed by ``(session_key, stream_id)`` so successive polls of the same exec
    session / tool stream share carry-over state. The interceptor owns one
    registry per turn context; :meth:`drop` (or :meth:`finalize_stream`) releases
    a stream once it completes so the buffer does not leak across turns.
    """

    def __init__(
        self,
        *,
        carry_over_chars: int = DEFAULT_CARRY_OVER_CHARS,
        sanitize_fn: SanitizeFn | None = None,
    ) -> None:
        self._carry_over = carry_over_chars
        self._sanitize_fn = sanitize_fn
        self._streams: dict[tuple[str, str], StreamingSanitizer] = {}

    def get(
        self,
        session_key: str,
        stream_id: str,
        *,
        turn_id: str | None = None,
    ) -> StreamingSanitizer:
        key = (session_key, stream_id)
        sanitizer = self._streams.get(key)
        if sanitizer is None:
            sanitizer = StreamingSanitizer(
                session_key,
                stream_id,
                turn_id=turn_id,
                carry_over_chars=self._carry_over,
                sanitize_fn=self._sanitize_fn,
            )
            self._streams[key] = sanitizer
        return sanitizer

    def has(self, session_key: str, stream_id: str) -> bool:
        return (session_key, stream_id) in self._streams

    async def finalize_stream(self, session_key: str, stream_id: str) -> str:
        """Finalize and drop the stream, returning its flushed tail."""
        sanitizer = self._streams.pop((session_key, stream_id), None)
        if sanitizer is None:
            return ""
        return await sanitizer.finalize()

    def drop(self, session_key: str, stream_id: str) -> None:
        self._streams.pop((session_key, stream_id), None)

    def clear(self) -> None:
        self._streams.clear()


__all__ = [
    "DEFAULT_CARRY_OVER_CHARS",
    "StreamingSanitizer",
    "StreamingSanitizerRegistry",
]
