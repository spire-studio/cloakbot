"""Stateful streaming output restorer with a carry-over tail (Cap A, inverse).

The model streams its reply **incrementally** as sanitized text — every chunk
still carries ``<<TAG_N>>`` placeholders (the model only ever saw placeholders,
and privacy mode tells it to use them). The webui must show the user the
*restored* values live, matching the (already-restored, ungated) final message.

Restoring each chunk in isolation is unsafe in exactly one way: a single
placeholder token can straddle a chunk boundary (``<<PER`` | ``SON_1>>``), and
restoring each half leaves the raw token fragments on screen.
:class:`StreamingRestorer` removes that seam. It buffers only a trailing
*partial token* — a tail that could still grow into a ``<<TAG_N>>`` — and emits
the restored form of everything before it. The held-back tail is re-examined on
the next chunk; :meth:`finalize` flushes whatever remains.

Why this is simpler than the input :class:`StreamingSanitizer`: restoration is a
*pure per-token substitution* (``restore_tokens`` replaces each complete token
independently, with no cross-token context), so a chunk cut at a point that is
outside every token restores identically whether done alone or as part of the
whole stream. Therefore concatenating every :meth:`feed` + :meth:`finalize`
output is **byte-for-byte equal** to ``restore_tokens(full_sanitized_output)`` —
which is what the final message and the turn-end restoration annotations index
into, so the Diff overlay's span offsets line up exactly.

One instance per stream segment (reset at ``on_stream_end``); placeholders never
straddle a segment boundary because a segment is one contiguous model generation.
"""

from __future__ import annotations

import re

from cloakbot.privacy.core.sanitization.restorer import restore_tokens
from cloakbot.privacy.core.state.vault import get_map

# A trailing run that could still grow into a ``<<TAG_N>>`` token: "<", "<<",
# "<<PER", "<<PERSON_1", "<<PERSON_1>" (at most one closing ">"). Anchored at
# end-of-buffer. A *complete* token ends in ">>" — two ">" can't both be consumed
# by the single optional ">?", so a finished token never matches and is emitted.
_PARTIAL_TAIL_RE = re.compile(r"<<?[A-Z0-9_]*>?$")

# Cap the held-back partial: a real token is short. If "<<…" grows past this with
# no ">>", it is not a placeholder, so stop withholding (bounds stream latency on
# literal "<<" text such as C++ shift operators).
_MAX_PARTIAL_CHARS = 128


class StreamingRestorer:
    """Restore ``<<TAG_N>>`` placeholders in an incrementally-streamed reply.

    Usage::

        r = StreamingRestorer(session_key)
        out1 = r.feed(chunk_1)   # restored text settled so far (may be "")
        out2 = r.feed(chunk_2)
        tail = r.finalize()      # flush the residual partial-token tail

    Each call returns the **newly settled** restored text. Concatenating every
    return value yields ``restore_tokens(chunk_1 + chunk_2 + …)``.
    """

    def __init__(self, session_key: str) -> None:
        self.session_key = session_key
        self._buf = ""  # un-emitted raw (placeholder) text

    def _settle_point(self) -> int:
        """Index up to which ``self._buf`` is safe to restore + emit.

        That is everything before a trailing partial token. A partial longer than
        ``_MAX_PARTIAL_CHARS`` cannot be a real token, so it is released.
        """
        match = _PARTIAL_TAIL_RE.search(self._buf)
        if match is None:
            return len(self._buf)
        start = match.start()
        if len(self._buf) - start > _MAX_PARTIAL_CHARS:
            return len(self._buf)
        return start

    def feed(self, delta: str) -> str:
        """Append *delta*; return any newly-settled restored text."""
        if not delta:
            return ""
        smap = get_map(self.session_key)
        # Fast path: no placeholders in this session and nothing buffered → pass
        # the chunk straight through, byte-identical to upstream (no privacy data
        # means nothing to restore and no token can ever appear).
        if not self._buf and not smap.placeholder_to_original and not smap.placeholder_to_entity:
            return delta
        self._buf += delta
        cut = self._settle_point()
        if cut <= 0:
            return ""
        settled, self._buf = self._buf[:cut], self._buf[cut:]
        return restore_tokens(settled, smap)

    def finalize(self) -> str:
        """Flush and restore the residual tail. Idempotent after first call."""
        if not self._buf:
            return ""
        settled, self._buf = self._buf, ""
        return restore_tokens(settled, get_map(self.session_key))


__all__ = ["StreamingRestorer"]
