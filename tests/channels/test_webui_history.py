from pathlib import Path

from fastapi.testclient import TestClient

from cloakbot.bus.queue import MessageBus
from cloakbot.channels.webui import WebUIChannel, WebUIConfig
from cloakbot.privacy.core.state.vault import _SessionMap, save_map, set_vault_workspace
from cloakbot.privacy.transparency.report import build_session_privacy_snapshot
from cloakbot.privacy.webui import WebUIPrivacyPayload, WebUIPrivacyTimeline, WebUIPrivacyTurn
from cloakbot.privacy.webui.history import append_webui_privacy_payload
from cloakbot.session.manager import Session, SessionManager


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
