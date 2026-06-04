"""Cap F — GET /api/sessions/{key}/privacy: rehydration + the localhost gate.

The additive history route is the third egress path for the raw-value-bearing
privacy payloads. It must apply the SAME blocking gate as the WS frame and the
tool-approval authorization: localhost rehydrates the full diff, any non-localhost
client gets the redacted projection only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cloakbot.privacy.core.state.vault import set_vault_workspace
from cloakbot.privacy.core.types import Severity
from cloakbot.privacy.transparency.report import (
    EntitySummary,
    SessionEntityData,
    SessionPrivacySnapshot,
)
from cloakbot.privacy.webui.contracts import (
    WebUIPrivacyPayload,
    WebUIPrivacyTimeline,
    WebUIPrivacyTurn,
    WebUIUserDocument,
)
from cloakbot.privacy.webui.history import append_webui_privacy_payload
from cloakbot.webui.privacy_routes import handle_privacy_route, is_privacy_route

RAW_NAME = "Alice Chen"
RAW_DOC = "raw secret doc body"


class _Conn:
    def __init__(self, remote: tuple[str, int] | None) -> None:
        self.remote_address = remote


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
                    created_turn="t1",
                    last_seen_turn="t1",
                )
            ],
            entity_counts=[EntitySummary(entity_type="PERSON", severity=Severity.HIGH, count=1)],
        ),
        privacyAnnotations=[],
        privacyTurn=WebUIPrivacyTurn(
            turnId="t1",
            intent="chat",
            remotePrompt="hi <<PERSON_1>>",
            localComputations=[],
            userDocuments=[
                WebUIUserDocument(
                    documentName="d.txt",
                    mimeType="text/plain",
                    originalSha256="x",
                    charCount=1,
                    originalText=RAW_DOC,
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
            turnId="t1", traceId="tr", totalDurationMs=0, stageDurationsMs={}, events=[]
        ),
    )


def _call(
    *,
    connection: Any,
    got: str,
    workspace: Path,
    token_ok: bool = True,
):
    return handle_privacy_route(
        connection=connection,
        got=got,
        workspace=workspace,
        decode_key=lambda raw: f"websocket:{raw}",
        is_websocket_session_key=lambda key: key.startswith("websocket:"),
        check_api_token=lambda: token_ok,
    )


def _body(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


def test_is_privacy_route_matching() -> None:
    assert is_privacy_route("/api/sessions/abc/privacy")
    assert not is_privacy_route("/api/sessions/abc/messages")
    assert not is_privacy_route("/api/sessions/abc/privacy/extra")


def test_non_privacy_path_returns_none(tmp_path: Path) -> None:
    resp = _call(connection=_Conn(("127.0.0.1", 1)), got="/api/sessions/x/messages", workspace=tmp_path)
    assert resp is None


def test_localhost_rehydrates_full_payload(tmp_path: Path) -> None:
    set_vault_workspace(tmp_path)
    append_webui_privacy_payload(tmp_path, "websocket:sess", _payload())
    resp = _call(connection=_Conn(("127.0.0.1", 1)), got="/api/sessions/sess/privacy", workspace=tmp_path)
    assert resp.status_code == 200
    body = _body(resp)
    assert body["localhost"] is True
    text = json.dumps(body["turns"], ensure_ascii=False)
    assert RAW_NAME in text
    assert RAW_DOC in text


def test_blocking_non_localhost_rehydration_has_zero_raw(tmp_path: Path) -> None:
    """THE blocking acceptance test at the HTTP history layer."""
    set_vault_workspace(tmp_path)
    append_webui_privacy_payload(tmp_path, "websocket:sess", _payload())
    resp = _call(connection=_Conn(("203.0.113.7", 1)), got="/api/sessions/sess/privacy", workspace=tmp_path)
    assert resp.status_code == 200
    body = _body(resp)
    assert body["localhost"] is False
    text = json.dumps(body["turns"], ensure_ascii=False)
    assert RAW_NAME not in text
    assert "Alice" not in text
    assert RAW_DOC not in text
    # placeholders still rehydrate so the overlay renders
    assert "<<PERSON_1>>" in text


def test_unauthenticated_request_is_rejected(tmp_path: Path) -> None:
    resp = _call(
        connection=_Conn(("127.0.0.1", 1)),
        got="/api/sessions/sess/privacy",
        workspace=tmp_path,
        token_ok=False,
    )
    assert resp.status_code == 401


def test_missing_history_returns_empty_turns(tmp_path: Path) -> None:
    set_vault_workspace(tmp_path)
    resp = _call(connection=_Conn(("127.0.0.1", 1)), got="/api/sessions/none/privacy", workspace=tmp_path)
    assert resp.status_code == 200
    assert _body(resp)["turns"] == []


def test_no_remote_address_treated_as_non_localhost(tmp_path: Path) -> None:
    """A connection without a remote_address must fail closed (not localhost)."""
    set_vault_workspace(tmp_path)
    append_webui_privacy_payload(tmp_path, "websocket:sess", _payload())
    resp = _call(connection=_Conn(None), got="/api/sessions/sess/privacy", workspace=tmp_path)
    body = _body(resp)
    assert body["localhost"] is False
    assert RAW_NAME not in json.dumps(body["turns"], ensure_ascii=False)
