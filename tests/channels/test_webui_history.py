from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from cloakbot.bus.queue import MessageBus
from cloakbot.channels.webui import WebUIChannel, WebUIConfig
from cloakbot.privacy.core.state.vault import _SessionMap, save_map, set_vault_workspace
from cloakbot.privacy.tool_models import ToolApprovalRequest
from cloakbot.privacy.transparency.report import build_session_privacy_snapshot
from cloakbot.privacy.webui import WebUIPrivacyPayload, WebUIPrivacyTimeline, WebUIPrivacyTurn
from cloakbot.privacy.webui.history import append_webui_privacy_payload
from cloakbot.session.manager import Session, SessionManager
from cloakbot.tool_privacy import ToolPrivacyClass


def test_webui_history_api_returns_messages_and_privacy_turns(tmp_path: Path) -> None:
    set_vault_workspace(tmp_path)
    session_key = "webui:session-1"

    smap = _SessionMap()
    smap.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="turn-1")
    save_map(session_key, smap)

    session = Session(key=session_key)
    session.add_message("user", "Hello <<PERSON_1>>")
    session.add_message("assistant", "Hi <<PERSON_1>>")
    SessionManager(tmp_path).save(session)

    append_webui_privacy_payload(
        tmp_path,
        session_key,
        WebUIPrivacyPayload(
            privacy=build_session_privacy_snapshot(session_key),
            privacyAnnotations=[],
            privacyTurn=WebUIPrivacyTurn(
                turnId="turn-1",
                intent="chat",
                remotePrompt="Hello <<PERSON_1>>",
                localComputations=[],
            ),
            privacyTimeline=WebUIPrivacyTimeline(
                turnId="turn-1",
                traceId="trace-1",
                totalDurationMs=0,
                stageDurationsMs={},
                events=[],
            ),
        ),
    )

    channel = WebUIChannel(
        WebUIConfig(enabled=True, status={"workspace": str(tmp_path)}),
        MessageBus(),
    )

    with TestClient(channel._app) as client:
        sessions = client.get("/api/sessions").json()["sessions"]
        detail = client.get("/api/sessions/session-1").json()

    assert sessions[0]["id"] == "session-1"
    assert sessions[0]["title"] == "Hello Alice Chen"
    assert detail["messages"][0]["content"] == "Hello Alice Chen"
    assert detail["messages"][1]["content"] == "Hi Alice Chen"
    assert detail["privacySnapshot"]["total_entities"] == 1
    assert detail["privacyTurns"][0]["remotePrompt"] == "Hello <<PERSON_1>>"


@pytest.mark.asyncio
async def test_webui_stream_end_resuming_does_not_emit_assistant_done(tmp_path: Path) -> None:
    channel = WebUIChannel(
        WebUIConfig(enabled=True, status={"workspace": str(tmp_path)}),
        MessageBus(),
    )
    channel._broadcast = AsyncMock()

    await channel.send_delta("session-1", "", {"_stream_end": True, "_resuming": True})

    channel._broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_webui_final_stream_end_emits_assistant_done(tmp_path: Path) -> None:
    channel = WebUIChannel(
        WebUIConfig(enabled=True, status={"workspace": str(tmp_path)}),
        MessageBus(),
    )
    channel._broadcast = AsyncMock()

    await channel.send_delta("session-1", "", {"_stream_end": True})

    channel._broadcast.assert_awaited_once()
    event = channel._broadcast.await_args.args[1]
    assert event["type"] == "assistant_done"


def test_webui_tool_approval_accepts_full_backend_request_payload() -> None:
    request = ToolApprovalRequest(
        approval_id="approval-1",
        session_key="webui:session-1",
        turn_id="turn-1",
        tool_call_id="call-1",
        tool_name="web_search",
        privacy_class=ToolPrivacyClass.EXTERNAL,
        remote_arguments={"query": "<<PERSON_1>> phone"},
        restored_arguments={"query": "Alice phone"},
    )

    approval = WebUIChannel._tool_approval_from_metadata({
        "tool_approval": request.model_dump(mode="json"),
    })

    assert approval is not None
    assert approval.approval_id == "approval-1"
    assert approval.tool_name == "web_search"
