"""Local WebUI channel hosted by the gateway process."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import AliasChoices, Field

from cloakbot.bus.events import OutboundMessage
from cloakbot.channels.base import BaseChannel
from cloakbot.config.schema import Base


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
            return {
                **self.status_payload,
                "ready": True,
                "frontendBuilt": self.frontend_dist_dir.exists(),
            }

        @app.websocket("/ws/chat")
        async def chat(websocket: WebSocket) -> None:
            session_id = websocket.query_params.get("session_id") or uuid4().hex
            await websocket.accept()
            self._clients.setdefault(session_id, set()).add(websocket)
            await websocket.send_json({"type": "session", "sessionId": session_id})
            await websocket.send_json(
                {
                    "type": "status",
                    "data": {
                        **self.status_payload,
                        "ready": True,
                        "frontendBuilt": self.frontend_dist_dir.exists(),
                    },
                }
            )

            try:
                while True:
                    payload = json.loads(await websocket.receive_text())
                    content = str(payload.get("content", "")).strip()
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
                {
                    "type": "progress",
                    "content": msg.content,
                    "toolHint": bool(msg.metadata.get("_tool_hint")),
                },
            )
            return

        await self._broadcast(
            msg.chat_id,
            {
                "type": "assistant_message",
                "content": msg.content,
            },
        )
        await self._broadcast(msg.chat_id, {"type": "assistant_done"})

    async def send_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        meta = metadata or {}
        if meta.get("_stream_end"):
            await self._broadcast(chat_id, {"type": "assistant_done"})
            return

        if delta:
            await self._broadcast(chat_id, {"type": "assistant_delta", "content": delta})

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
