"""Cap F — PrivacyWebSocketChannel: side-channel emission + per-connection gate.

The channel folds the (gated) WebUIPrivacyPayload into ``_agent_ui.privacy`` on
the normal ``message`` frame and fires standalone privacy frames. The blocking
invariant is enforced PER CONNECTION: a localhost peer gets the cleartext, a
non-localhost peer on the SAME chat gets the redacted projection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloakbot.bus.events import OutboundMessage
from cloakbot.channels.websocket import WebSocketChannel, WebSocketConfig
from cloakbot.channels.websocket_privacy import PrivacyWebSocketChannel
from cloakbot.privacy.core.types import Severity
from cloakbot.privacy.transparency.report import (
    EntitySummary,
    SessionEntityData,
    SessionPrivacySnapshot,
)
from cloakbot.privacy.webui.contracts import (
    WEBUI_PRIVACY_METADATA_KEY,
    WebUIPrivacyPayload,
    WebUIPrivacyTimeline,
    WebUIPrivacyTurn,
    WebUIUserDocument,
)
from cloakbot.webui.gateway_services import build_gateway_services

RAW_NAME = "Alice Chen"
RAW_DOC_TEXT = "raw secret document body"


def _gateway(bus: Any) -> Any:
    cfg = WebSocketConfig.model_validate(
        {
            "enabled": True,
            "allowFrom": ["*"],
            "host": "127.0.0.1",
            "port": 29999,
            "path": "/ws",
            "websocketRequiresToken": False,
        }
    )
    return build_gateway_services(
        config=cfg,
        bus=bus,
        session_manager=None,
        static_dist_path=None,
        workspace_path=Path.cwd(),
        default_restrict_to_workspace=False,
        runtime_model_name=None,
        runtime_surface="browser",
        runtime_capabilities_overrides=None,
    )


def _channel() -> PrivacyWebSocketChannel:
    bus = MagicMock()
    return PrivacyWebSocketChannel(
        {"enabled": True, "allowFrom": ["*"]}, bus, gateway=_gateway(bus)
    )


def _conn(remote: tuple[str, int] | None) -> AsyncMock:
    c = AsyncMock()
    c.remote_address = remote
    return c


def _payload() -> WebUIPrivacyPayload:
    return WebUIPrivacyPayload(
        privacy=SessionPrivacySnapshot(
            total_entities=1,
            entities=[
                SessionEntityData(
                    placeholder="<<PERSON_1>>",
                    entity_type="PERSON",
                    severity=Severity.HIGH,
                    canonical=RAW_NAME,
                    aliases=["Alice"],
                    value=RAW_NAME,
                    created_turn="turn-1",
                    last_seen_turn="turn-1",
                )
            ],
            entity_counts=[EntitySummary(entity_type="PERSON", severity=Severity.HIGH, count=1)],
        ),
        privacyAnnotations=[],
        privacyTurn=WebUIPrivacyTurn(
            turnId="turn-1",
            intent="chat",
            remotePrompt="hi <<PERSON_1>>",
            localComputations=[],
            userDocuments=[
                WebUIUserDocument(
                    documentName="d.txt",
                    mimeType="text/plain",
                    originalSha256="x",
                    charCount=1,
                    originalText=RAW_DOC_TEXT,
                    sanitizedText="<<DOC_1>>",
                    sanitizedPreview="<<DOC_1>>",
                    chunksTotal=1,
                    chunksFailed=False,
                    wasSanitized=True,
                    entityTypes=["PERSON"],
                )
            ],
        ),
        privacyTimeline=WebUIPrivacyTimeline(
            turnId="turn-1",
            traceId="t",
            totalDurationMs=0,
            stageDurationsMs={},
            events=[],
        ),
    )


def _sent_texts(conn: AsyncMock) -> list[str]:
    return [c.args[0] for c in conn.send.await_args_list]


def _frames(conn: AsyncMock) -> list[dict]:
    return [json.loads(t) for t in _sent_texts(conn)]


# The message content is the user-visible (locally-restored) reply; it is NOT a
# side-channel leak. To assert the gate strips the *side-channel* raw values, keep
# the visible message free of the raw vault values so a raw-value hit can only come
# from the privacy blob / standalone frames.
_VISIBLE_CONTENT = "your request is done"


def _msg(payload: WebUIPrivacyPayload | None) -> OutboundMessage:
    meta: dict = {"webui": True}
    if payload is not None:
        meta[WEBUI_PRIVACY_METADATA_KEY] = payload
    return OutboundMessage(
        channel="websocket", chat_id="chat-1", content=_VISIBLE_CONTENT, metadata=meta
    )


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_payload_delegates_to_parent_unchanged() -> None:
    """A frame without a privacy blob behaves exactly like the base channel."""
    ch = _channel()
    conn = _conn(("127.0.0.1", 5))
    ch._attach(conn, "chat-1")
    await ch.send(_msg(None))
    frames = _frames(conn)
    msg_frames = [f for f in frames if f.get("event") == "message"]
    assert len(msg_frames) == 1
    assert "agent_ui" not in msg_frames[0]
    # no standalone privacy frames either
    assert not any(f.get("event", "").startswith("privacy_") for f in frames)


@pytest.mark.asyncio
async def test_localhost_message_carries_agent_ui_privacy_with_raw() -> None:
    ch = _channel()
    conn = _conn(("127.0.0.1", 5))
    ch._attach(conn, "chat-1")
    await ch.send(_msg(_payload()))
    frames = _frames(conn)
    msg_frame = next(f for f in frames if f.get("event") == "message")
    assert "privacy" in msg_frame["agent_ui"]
    assert msg_frame["agent_ui"]["privacy"]["privacy"]["entities"][0]["canonical"] == RAW_NAME


@pytest.mark.asyncio
async def test_localhost_gets_standalone_privacy_frames() -> None:
    ch = _channel()
    conn = _conn(("127.0.0.1", 5))
    ch._attach(conn, "chat-1")
    await ch.send(_msg(_payload()))
    events = [f.get("event") for f in _frames(conn)]
    assert "privacy_snapshot" in events
    assert "privacy_trace" in events


@pytest.mark.asyncio
async def test_blocking_non_localhost_receives_zero_raw_values() -> None:
    """THE blocking acceptance test at the channel transport layer."""
    ch = _channel()
    conn = _conn(("203.0.113.7", 5))  # public IP, not localhost
    ch._attach(conn, "chat-1")
    await ch.send(_msg(_payload()))
    blob = json.dumps(_frames(conn), ensure_ascii=False)
    assert RAW_NAME not in blob
    assert "Alice" not in blob
    assert RAW_DOC_TEXT not in blob
    # but the placeholder + the message text the user typed still flow
    assert "<<PERSON_1>>" in blob


@pytest.mark.asyncio
async def test_mixed_connections_gate_per_connection() -> None:
    """Same chat, two peers: localhost sees raw, remote sees redacted — at once."""
    ch = _channel()
    local = _conn(("127.0.0.1", 5))
    remote = _conn(("203.0.113.7", 5))
    ch._attach(local, "chat-1")
    ch._attach(remote, "chat-1")
    await ch.send(_msg(_payload()))

    local_blob = json.dumps(_frames(local), ensure_ascii=False)
    remote_blob = json.dumps(_frames(remote), ensure_ascii=False)
    assert RAW_NAME in local_blob
    assert RAW_DOC_TEXT in local_blob
    assert RAW_NAME not in remote_blob
    assert RAW_DOC_TEXT not in remote_blob
    # both still get the message
    assert any(f.get("event") == "message" for f in _frames(local))
    assert any(f.get("event") == "message" for f in _frames(remote))


@pytest.mark.asyncio
async def test_subscriber_set_restored_after_grouped_send() -> None:
    """The temporary _subs narrowing must always be restored."""
    ch = _channel()
    local = _conn(("127.0.0.1", 5))
    remote = _conn(("203.0.113.7", 5))
    ch._attach(local, "chat-1")
    ch._attach(remote, "chat-1")
    await ch.send(_msg(_payload()))
    assert ch._subs["chat-1"] == {local, remote}


@pytest.mark.asyncio
async def test_invalid_payload_falls_back_to_plain_message() -> None:
    ch = _channel()
    conn = _conn(("127.0.0.1", 5))
    ch._attach(conn, "chat-1")
    msg = OutboundMessage(
        channel="websocket",
        chat_id="chat-1",
        content="hello",
        metadata={"webui": True, WEBUI_PRIVACY_METADATA_KEY: {"not": "a payload"}},
    )
    await ch.send(msg)
    frames = _frames(conn)
    msg_frame = next(f for f in frames if f.get("event") == "message")
    assert msg_frame["text"] == "hello"
    # bad blob never forwarded
    assert "agent_ui" not in msg_frame or "privacy" not in msg_frame.get("agent_ui", {})


@pytest.mark.asyncio
async def test_upstream_client_ignores_unknown_privacy_frames() -> None:
    """Additive-ignore: privacy frames are extra events an upstream client drops.

    The standalone frames use event names absent from upstream's switch; this
    asserts the message frame remains a valid, self-contained upstream frame so a
    privacy-unaware client renders the conversation unchanged.
    """
    ch = _channel()
    conn = _conn(("127.0.0.1", 5))
    ch._attach(conn, "chat-1")
    await ch.send(_msg(_payload()))
    msg_frame = next(f for f in _frames(conn) if f.get("event") == "message")
    # The upstream-required fields are present and well-formed.
    assert msg_frame["chat_id"] == "chat-1"
    assert msg_frame["text"] == _VISIBLE_CONTENT


@pytest.mark.asyncio
async def test_l1_raw_privacy_blob_not_persisted_to_transcript(monkeypatch) -> None:
    """[Cap F / L1] The raw localhost ``agent_ui.privacy`` blob must NOT be
    written to the webui transcript.

    The live localhost frame carries raw entity values / original document text
    by design (gated per-connection). The on-disk transcript has no localhost
    gate and replay would re-broadcast it ungated, so the persisted copy must
    strip the ``privacy`` projection. We capture every transcript append and
    assert no raw vault value reaches it.
    """
    import cloakbot.channels.websocket as ws_mod

    appended: list[Any] = []
    monkeypatch.setattr(
        ws_mod, "append_transcript_object", lambda sk, obj: appended.append((sk, obj))
    )

    ch = _channel()
    conn = _conn(("127.0.0.1", 5))  # localhost: the live frame DOES carry raw
    ch._attach(conn, "chat-1")
    await ch.send(_msg(_payload()))

    # Sanity: the live localhost frame still carried the raw blob (gate unchanged).
    live_blob = json.dumps(_frames(conn), ensure_ascii=False)
    assert RAW_NAME in live_blob

    # The persisted transcript carries ZERO raw vault values and no privacy blob.
    transcript_blob = json.dumps(appended, ensure_ascii=False)
    assert appended, "no transcript append captured"
    assert RAW_NAME not in transcript_blob
    assert RAW_DOC_TEXT not in transcript_blob
    for _sk, obj in appended:
        agent_ui = obj.get("agent_ui") if isinstance(obj, dict) else None
        if isinstance(agent_ui, dict):
            assert "privacy" not in agent_ui, "raw privacy blob persisted to transcript"
    # The transcript still records the visible message text (non-secret).
    assert any(
        isinstance(obj, dict) and obj.get("text") == _VISIBLE_CONTENT
        for _sk, obj in appended
    )


def test_privacy_channel_is_websocket_subclass() -> None:
    assert issubclass(PrivacyWebSocketChannel, WebSocketChannel)
    assert PrivacyWebSocketChannel.name == "websocket"
