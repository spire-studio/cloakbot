"""Local WebUI channel hosted by the gateway process."""

from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import AliasChoices, Field, ValidationError

from cloakbot.bus.events import OutboundMessage
from cloakbot.channels.base import BaseChannel
from cloakbot.config.paths import get_workspace_path
from cloakbot.config.schema import Base
from cloakbot.privacy.core.sanitization.restorer import (
    restore_tokens,
    restore_tokens_with_annotations,
)
from cloakbot.privacy.core.state.vault import get_map, set_vault_workspace
from cloakbot.privacy.transparency.report import build_session_privacy_snapshot
from cloakbot.privacy.webui import (
    WEBUI_PRIVACY_METADATA_KEY,
    WebUIAssistantDeltaEvent,
    WebUIAssistantDoneEvent,
    WebUIAssistantMessageEvent,
    WebUIPrivacyPayload,
    WebUIPrivacySnapshotEvent,
    WebUIProgressEvent,
    WebUISessionEvent,
    WebUIStatusData,
    WebUIStatusEvent,
    WebUIUserMessage,
)
from cloakbot.privacy.webui.history import load_webui_privacy_payloads
from cloakbot.session.manager import Session, SessionManager


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


class EmbeddedUvicornServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        return


class WebUIConfig(Base):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 18790
    streaming: bool = True
    allow_from: list[str] = Field(default_factory=lambda: ["*"])
    frontend_url: str | None = None
    status: dict[str, str | bool] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("_status", "status"),
        serialization_alias="_status",
    )


class WebUIChannel(BaseChannel):
    name = "webui"
    display_name = "WebUI"

    def __init__(self, config, bus):
        if isinstance(config, dict):
            config = WebUIConfig.model_validate(config)
        super().__init__(config, bus)
        self.config: WebUIConfig = config
        self.host = self.config.host
        self.port = self.config.port
        self.frontend_url = self.config.frontend_url or ""
        self.status_payload = dict(self.config.status)
        workspace_value = self.status_payload.get("workspace")
        self.workspace = get_workspace_path(workspace_value if isinstance(workspace_value, str) else None)
        set_vault_workspace(self.workspace)
        self.sessions = SessionManager(self.workspace)
        self.frontend_dist_dir = Path(__file__).resolve().parents[2] / "webui" / "dist"
        self._clients: dict[str, set[WebSocket]] = {}
        self._server: EmbeddedUvicornServer | None = None
        self._app = self._create_app()

    @classmethod
    def default_config(cls) -> dict:
        return WebUIConfig().model_dump(by_alias=True)

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="Cloakbot WebUI Gateway")
        origins = ["http://127.0.0.1:5173", "http://localhost:5173"]
        if self.frontend_url:
            origins.append(self.frontend_url)
        spa_files = None
        if self.frontend_dist_dir.exists() and not self.frontend_url:
            spa_files = SPAStaticFiles(directory=self.frontend_dist_dir, html=True, check_dir=False)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/api/status")
        async def status() -> dict:
            return WebUIStatusData.model_validate({
                **self.status_payload,
                "ready": True,
                "frontendBuilt": self.frontend_dist_dir.exists(),
            }).model_dump(mode="json", by_alias=True)

        @app.get("/api/sessions")
        async def sessions() -> dict:
            items = []
            for item in self.sessions.list_sessions():
                key = item.get("key") or ""
                if not key.startswith(f"{self.name}:"):
                    continue
                session = self.sessions.get_or_create(key)
                session_id = key.split(":", 1)[1]
                items.append({
                    "id": session_id,
                    "title": self._session_title(session),
                    "createdAt": self._timestamp_ms(item.get("created_at")),
                    "updatedAt": self._timestamp_ms(item.get("updated_at")),
                })
            return {"sessions": items}

        @app.get("/api/sessions/{session_id}")
        async def session_history(session_id: str) -> dict:
            session_key = f"{self.name}:{session_id}"
            if not any((item.get("key") or "") == session_key for item in self.sessions.list_sessions()):
                raise HTTPException(status_code=404, detail="Session not found")
            session = self.sessions.get_or_create(session_key)
            payloads = load_webui_privacy_payloads(self.workspace, session_key)
            return {
                "id": session_id,
                "title": self._session_title(session),
                "messages": self._history_messages(session, payloads),
                "privacySnapshot": build_session_privacy_snapshot(session_key).model_dump(mode="json"),
                "privacyTurns": [
                    payload.privacy_turn.model_dump(mode="json", by_alias=True)
                    for payload in payloads
                ],
                "createdAt": self._timestamp_ms(session.created_at.isoformat()),
                "updatedAt": self._timestamp_ms(session.updated_at.isoformat()),
            }

        @app.websocket("/ws/chat")
        async def chat(websocket: WebSocket) -> None:
            session_id = websocket.query_params.get("session_id") or uuid4().hex
            await websocket.accept()
            self._clients.setdefault(session_id, set()).add(websocket)
            await websocket.send_json(
                WebUISessionEvent(session_id=session_id).model_dump(mode="json", by_alias=True)
            )
            await websocket.send_json(
                WebUIStatusEvent(
                    data=WebUIStatusData.model_validate({
                        **self.status_payload,
                        "ready": True,
                        "frontendBuilt": self.frontend_dist_dir.exists(),
                    })
                ).model_dump(mode="json", by_alias=True)
            )
            await websocket.send_json(
                WebUIPrivacySnapshotEvent(
                    data=build_session_privacy_snapshot(f"{self.name}:{session_id}"),
                ).model_dump(mode="json", by_alias=True)
            )

            try:
                while True:
                    try:
                        payload = WebUIUserMessage.model_validate_json(await websocket.receive_text())
                    except ValidationError:
                        continue
                    content = payload.content.strip()
                    if not content:
                        continue
                    await self._handle_message(
                        sender_id=session_id,
                        chat_id=session_id,
                        content=content,
                    )
            except WebSocketDisconnect:
                pass
            finally:
                self._discard_client(session_id, websocket)

        if self.frontend_url:
            @app.get("/", include_in_schema=False)
            async def webui_dev_root() -> RedirectResponse:
                return RedirectResponse(self.frontend_url)

        elif spa_files is not None:
            @app.get("/", include_in_schema=False)
            async def webui_index(request: Request):
                return await spa_files.get_response("index.html", request.scope)

            @app.get("/{path:path}", include_in_schema=False)
            async def webui_asset(path: str, request: Request):
                return await spa_files.get_response(path or "index.html", request.scope)

        return app

    def _session_title(self, session: Session) -> str:
        smap = get_map(session.key)
        for message in session.messages:
            if message.get("role") != "user":
                continue
            content = self._message_text(message.get("content"))
            if not content:
                continue
            title = " ".join(restore_tokens(content, smap).strip().split())
            if not title:
                return "New chat"
            return title[:47] + "..." if len(title) > 48 else title
        return "New chat"

    def _history_messages(
        self,
        session: Session,
        payloads: list[WebUIPrivacyPayload],
    ) -> list[dict]:
        smap = get_map(session.key)
        messages = []
        assistant_payload_index = 0

        for index, message in enumerate(session.messages[session.last_consolidated:]):
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue

            content = self._message_text(message.get("content"))
            if role == "assistant" and not content:
                continue

            created_at = self._timestamp_ms(message.get("timestamp"))
            restored, annotations = restore_tokens_with_annotations(content, smap)
            entry = {
                "id": f"{session.key}:{index}",
                "role": role,
                "content": restored,
                "createdAt": created_at,
            }

            if role == "assistant":
                payload = payloads[assistant_payload_index] if assistant_payload_index < len(payloads) else None
                assistant_payload_index += 1
                if payload is not None:
                    annotations = payload.privacy_annotations
                    entry["assistantStatus"] = {
                        "state": "done",
                        "startedAt": created_at,
                        "finishedAt": created_at,
                        "privacyTimeline": payload.privacy_timeline.model_dump(mode="json", by_alias=True),
                    }
                else:
                    entry["assistantStatus"] = {
                        "state": "done",
                        "startedAt": created_at,
                        "finishedAt": created_at,
                    }
                entry["privacyAnnotations"] = [
                    annotation.model_dump(mode="json", by_alias=True)
                    for annotation in annotations
                ]

            messages.append(entry)

        return messages

    @staticmethod
    def _message_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            return "\n".join(parts)
        return ""

    @staticmethod
    def _timestamp_ms(value: object) -> int:
        if isinstance(value, datetime):
            return int(value.timestamp() * 1000)
        if isinstance(value, str) and value:
            try:
                return int(datetime.fromisoformat(value).timestamp() * 1000)
            except ValueError:
                pass
        return int(datetime.now().timestamp() * 1000)

    async def start(self) -> None:
        self._running = True
        logger.info("Starting WebUI channel on http://{}:{}", self.host, self.port)
        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = EmbeddedUvicornServer(config)
        try:
            await self._server.serve()
        finally:
            self._running = False

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True

        for sockets in self._clients.values():
            for socket in list(sockets):
                with contextlib.suppress(Exception):
                    await socket.close()
        self._clients.clear()
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        if msg.metadata.get("_progress"):
            await self._broadcast(
                msg.chat_id,
                WebUIProgressEvent(
                    content=msg.content,
                    tool_hint=bool(msg.metadata.get("_tool_hint")),
                ).model_dump(mode="json", by_alias=True),
            )
            return

        privacy_fields = self._privacy_event_fields(msg.metadata)
        await self._broadcast(
            msg.chat_id,
            WebUIAssistantMessageEvent(
                content=msg.content,
                **privacy_fields,
            ).model_dump(mode="json", by_alias=True),
        )
        await self._broadcast(
            msg.chat_id,
            WebUIAssistantDoneEvent(**privacy_fields).model_dump(mode="json", by_alias=True),
        )

    async def send_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        meta = metadata or {}
        if meta.get("_stream_end"):
            privacy_fields = self._privacy_event_fields(meta)
            await self._broadcast(
                chat_id,
                WebUIAssistantDoneEvent(**privacy_fields).model_dump(mode="json", by_alias=True),
            )
            return

        if delta:
            await self._broadcast(
                chat_id,
                WebUIAssistantDeltaEvent(content=delta).model_dump(mode="json", by_alias=True),
            )

    def _privacy_event_fields(self, metadata: dict[str, object]) -> dict[str, object]:
        raw_payload = metadata.get(WEBUI_PRIVACY_METADATA_KEY)
        if raw_payload is None:
            return {}

        try:
            payload = (
                raw_payload
                if isinstance(raw_payload, WebUIPrivacyPayload)
                else WebUIPrivacyPayload.model_validate(raw_payload)
            )
        except ValidationError:
            logger.warning("webui: invalid privacy payload skipped")
            return {}

        return {
            "privacy": payload.privacy,
            "privacy_annotations": payload.privacy_annotations,
            "privacy_turn": payload.privacy_turn,
            "privacy_timeline": payload.privacy_timeline,
        }

    async def _broadcast(self, chat_id: str, event: dict[str, object]) -> None:
        clients = list(self._clients.get(chat_id, set()))
        for websocket in clients:
            try:
                await websocket.send_json(event)
            except Exception:
                self._discard_client(chat_id, websocket)

    def _discard_client(self, chat_id: str, websocket: WebSocket) -> None:
        clients = self._clients.get(chat_id)
        if not clients:
            return
        clients.discard(websocket)
        if not clients:
            self._clients.pop(chat_id, None)
