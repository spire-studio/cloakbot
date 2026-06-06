"""Privacy-aware WebSocket channel: the side-channel egress gate on the gateway.

``PrivacyWebSocketChannel`` is a thin subclass of upstream's
:class:`~cloakbot.channels.websocket.WebSocketChannel`. It re-homes the privacy
emission that used to live in the bespoke ``channels/webui.py`` onto the upstream
gateway with **zero** fork of the parent's frame logic:

- At send time it reads ``OutboundMessage.metadata[WEBUI_PRIVACY_METADATA_KEY]``.
  When absent (every non-webui channel, and webui turns with nothing to report)
  it delegates straight to the parent, so behaviour is byte-identical to upstream.
  When present it (a) folds the (gated) payload under
  ``metadata["_agent_ui"]["privacy"]`` so the parent's existing ``agent_ui``
  passthrough forwards it inside the normal ``message`` frame, and (b) fires the
  standalone ``privacy_snapshot`` / ``privacy_trace`` / ``tool_approval`` frames.

- The **blocking localhost gate** is applied per connection: the full
  raw-bearing payload reaches only ``_is_localhost(connection)`` connections; any
  other connection receives the redacted projection. Because the gate depends on
  the connection, the privacy blob is rendered per recipient — the override
  splits the subscriber set into a localhost group and a remote group and runs
  the parent's ``send`` once per group with a group-appropriate gated blob.

The transcript that the HTTP history route reads back is written from the
localhost-gated metadata, and that route applies the same gate again on read, so
no raw value is ever persisted into a frame a remote client could fetch.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from cloakbot.bus.events import OutboundMessage
from cloakbot.channels.websocket import WebSocketChannel
from cloakbot.privacy.webui.contracts import (
    WEBUI_PRIVACY_METADATA_KEY,
    WebUIPrivacyPayload,
)
from cloakbot.privacy.webui.side_channel import (
    merge_privacy_into_agent_ui,
    privacy_side_channel_frames,
)
from cloakbot.webui.http_utils import is_localhost as _is_localhost


def _coerce_payload(raw: Any) -> WebUIPrivacyPayload | None:
    """Validate the metadata blob into a typed payload, or ``None`` on bad input."""
    if raw is None:
        return None
    if isinstance(raw, WebUIPrivacyPayload):
        return raw
    try:
        return WebUIPrivacyPayload.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError + anything malformed
        logger.warning("websocket_privacy: invalid privacy payload skipped: {}", exc)
        return None


def _strip_privacy_metadata(msg: OutboundMessage) -> OutboundMessage:
    """Return a copy of *msg* with the privacy blob removed from metadata."""
    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=msg.content,
        media=msg.media,
        reply_to=msg.reply_to,
        metadata={k: v for k, v in msg.metadata.items() if k != WEBUI_PRIVACY_METADATA_KEY},
    )


class PrivacyWebSocketChannel(WebSocketChannel):
    """WebSocket channel that emits the privacy side-channel with a localhost gate."""

    name = "websocket"
    display_name = "WebSocket"

    async def send(self, msg: OutboundMessage) -> None:
        """Send *msg*, routing any attached privacy payload through the gate."""
        raw_payload = msg.metadata.get(WEBUI_PRIVACY_METADATA_KEY)
        if raw_payload is None:
            await super().send(msg)
            return

        payload = _coerce_payload(raw_payload)
        if payload is None:
            await super().send(_strip_privacy_metadata(msg))
            return

        conns = list(self._subs.get(msg.chat_id, ()))
        if not conns:
            # No subscribers: let the parent log the no-sub case, but never
            # persist the privacy blob to transcript.
            await super().send(_strip_privacy_metadata(msg))
            return

        local_conns = [c for c in conns if _is_localhost(c)]
        remote_conns = [c for c in conns if not _is_localhost(c)]

        if msg.metadata.get("_streamed"):
            # [buffering PrivacyHook] A streamed turn already delivered its content
            # via deltas; this final frame exists only to deliver the per-message
            # restoration annotations LIVE. Send a localhost-only settle frame
            # (gated _agent_ui.privacy, marked ``streamed`` so the client binds onto
            # the streamed message without re-rendering) + the standalone privacy
            # frames. Do NOT persist to the transcript — a refresh rehydrates from
            # the delta replay + GET /privacy, which already validate offsets.
            # Remote subscribers already received the streamed content and get no
            # raw annotations by design, so they are skipped here.
            if local_conns:
                await self._send_message_group(
                    msg, payload, conns=local_conns, is_localhost=True, persist=False
                )
                await self._send_standalone_privacy_frames(
                    local_conns, payload, is_localhost=True
                )
            return

        # Main message frame: delegate to the parent once per group with the
        # group-appropriate gated _agent_ui blob already merged in. The parent
        # owns media signing + transcript append + the standard frame shape.
        if local_conns:
            await self._send_message_group(msg, payload, conns=local_conns, is_localhost=True)
        if remote_conns:
            await self._send_message_group(msg, payload, conns=remote_conns, is_localhost=False)

        # Standalone frames (privacy_snapshot / privacy_trace / tool_approval).
        if local_conns:
            await self._send_standalone_privacy_frames(local_conns, payload, is_localhost=True)
        if remote_conns:
            await self._send_standalone_privacy_frames(remote_conns, payload, is_localhost=False)

    async def _send_message_group(
        self,
        msg: OutboundMessage,
        payload: WebUIPrivacyPayload,
        *,
        conns: list[Any],
        is_localhost: bool,
        persist: bool = True,
    ) -> None:
        """Delegate the main message frame to the parent, restricted to *conns*,
        with the gated privacy blob folded into ``_agent_ui``.

        The subscriber set is temporarily narrowed to *conns* so the parent's
        fan-out (and its single transcript append) targets exactly this group;
        it is always restored, even on error. ``persist=False`` skips the
        transcript append (used for the streamed settle frame, which must not
        re-persist a turn the deltas already recorded).
        """
        metadata = {k: v for k, v in msg.metadata.items() if k != WEBUI_PRIVACY_METADATA_KEY}
        merge_privacy_into_agent_ui(metadata, payload, is_localhost=is_localhost)
        scoped = OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=msg.content,
            media=msg.media,
            reply_to=msg.reply_to,
            metadata=metadata,
        )
        original = self._subs.get(msg.chat_id)
        self._subs[msg.chat_id] = set(conns)
        try:
            await super().send(scoped, persist=persist)
        finally:
            if original is None:
                self._subs.pop(msg.chat_id, None)
            else:
                self._subs[msg.chat_id] = original

    async def _send_standalone_privacy_frames(
        self,
        conns: list[Any],
        payload: WebUIPrivacyPayload,
        *,
        is_localhost: bool,
    ) -> None:
        if not conns:
            return
        frames = privacy_side_channel_frames(payload, is_localhost=is_localhost)
        for frame in frames:
            raw = json.dumps(frame, ensure_ascii=False)
            for connection in conns:
                await self._safe_send_to(connection, raw, label=f" {frame.get('event', 'privacy')} ")
