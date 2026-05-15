"""Local WebUI channel hosted by the gateway process."""

from __future__ import annotations

import contextlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any
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
    WebUIToolApproval,
    WebUIUserMessage,
)
from cloakbot.privacy.webui.history import load_webui_privacy_payloads
from cloakbot.session.manager import Session, SessionManager


_MATH_CONTRACT_PATTERN = re.compile(
    r"###\s*PRIVACY MODE ENABLED\s*###.*?###\s*END PRIVACY MATH CONTRACT\s*###",
    flags=re.DOTALL,
)


def _mime_from_data_url(value: object) -> str:
    """Extract the MIME type from a ``data:<mime>;base64,...`` URL.

    Returns ``image/png`` as a safe default for malformed inputs — the
    frontend ``<img>`` tag tolerates a mismatch between declared and
    actual MIME, and the redacted PNG path is the production-common
    case so this is the right fallback.
    """
    if not isinstance(value, str) or not value.startswith("data:"):
        return "image/png"
    head, _, _ = value.partition(";")
    mime = head.removeprefix("data:")
    return mime or "image/png"


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
                    if payload.type == "tool_approval":
                        if not payload.approval_id:
                            continue
                        await self._handle_message(
                            sender_id=session_id,
                            chat_id=session_id,
                            content="",
                            metadata={
                                "tool_approval": True,
                                "approval_id": payload.approval_id,
                                "approved": payload.approved,
                            },
                        )
                        continue

                    content = payload.content.strip()
                    media = [
                        attachment.data_url
                        for attachment in payload.attachments
                        if attachment.data_url
                    ]
                    if not content and not media:
                        continue
                    await self._handle_message(
                        sender_id=session_id,
                        chat_id=session_id,
                        content=content,
                        media=media or None,
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
            user_text, _images = self._extract_message_parts(message.get("content"))
            if not user_text:
                continue
            title = " ".join(restore_tokens(user_text, smap).strip().split())
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
        # A single peek/consume cursor: user messages peek the next turn
        # payload (to pull userAttachments), assistant messages then
        # consume it (to pull annotations + timeline). Tool-approval
        # assistant messages do not consume — they share the payload
        # with the *next* real assistant turn.
        payload_cursor = 0

        for index, message in enumerate(session.messages[session.last_consolidated:]):
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue

            user_text, image_blocks = self._extract_message_parts(message.get("content"))
            if role == "assistant" and not user_text:
                continue

            created_at = self._timestamp_ms(message.get("timestamp"))
            restored, annotations = restore_tokens_with_annotations(user_text, smap)
            entry: dict[str, Any] = {
                "id": f"{session.key}:{index}",
                "role": role,
                "content": restored,
                "createdAt": created_at,
            }

            if role == "user":
                peek_payload = (
                    payloads[payload_cursor] if payload_cursor < len(payloads) else None
                )
                # Two sources of truth for attachments on rehydration:
                # 1. ``image_blocks`` from session.messages — present for
                #    channels that keep image_url blocks in history.
                # 2. ``peek_payload.privacy_turn.user_attachments`` from
                #    the per-turn jsonl — present for the WebUI channel,
                #    where ``agent.loop`` strips binary blocks at save
                #    time. We prefer the payload because it carries the
                #    full redaction record (boxes/labels/status) and the
                #    redacted PNG was already base64-encoded server-side.
                persisted_attachments = self._attachments_from_image_blocks(image_blocks)
                attachment_results = self._attachment_results_from_payload(peek_payload)
                if not persisted_attachments and attachment_results:
                    # Prefer the original image (the user's actual upload)
                    # for the local-view bubble; fall back to the redacted
                    # version when the original wasn't persisted (older
                    # turns from before this artifact kind existed).
                    persisted_attachments = []
                    for result in attachment_results:
                        source = result.get("originalDataUrl") or result.get("redactedDataUrl")
                        if not isinstance(source, str):
                            continue
                        persisted_attachments.append(
                            {
                                "mimeType": _mime_from_data_url(source),
                                "dataUrl": source,
                            }
                        )
                if persisted_attachments:
                    entry["attachments"] = persisted_attachments
                if attachment_results:
                    entry["attachmentResults"] = attachment_results

            if role == "assistant":
                tool_approval = self._tool_approval_from_message(message)
                if tool_approval is not None:
                    entry["toolApproval"] = tool_approval.model_dump(mode="json", by_alias=True)
                    payload = None
                else:
                    payload = (
                        payloads[payload_cursor] if payload_cursor < len(payloads) else None
                    )
                    payload_cursor += 1
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
    def _extract_message_parts(content: object) -> tuple[str, list[dict[str, Any]]]:
        """Split a stored message into user-visible text + image blocks.

        Sanitization scaffolding the LLM consumed is **not** user
        content and must not surface in the chat history view:

        - Text blocks whose payload starts with one of the framing
          tags (region-map, OCR transcript, fail-closed omit notice)
          are dropped wholesale.
        - The math-mode privacy contract that ``MathAgent.prepare_input``
          appends to math turns is excised in-line from any text block
          containing it, so the user-visible portion that came before
          (or after) the contract is preserved.

        Image blocks are returned as-is so the caller can lift them
        into ``attachments`` for the frontend rehydration path.
        """
        if isinstance(content, str):
            return WebUIChannel._strip_inline_scaffolding(content), []
        if not isinstance(content, list):
            return "", []

        scaffold_prefixes = (
            "[Image redaction map",
            "[Local OCR transcript",
            "[visual content omitted;",
            # ``agent.loop._filter_for_history`` rewrites image_url blocks
            # to ``[image]`` / ``[image: <path>]`` / ``[image omitted]``
            # before persistence to keep session memory bounded. We never
            # want those markers in the chat bubble — the actual redacted
            # image is rehydrated from the turn payload instead.
            "[image]",
            "[image:",
            "[image omitted]",
        )

        user_text_parts: list[str] = []
        image_blocks: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "image_url":
                image_blocks.append(block)
                continue
            if btype == "text":
                text = block.get("text", "")
                if not isinstance(text, str) or not text:
                    continue
                if text.startswith(scaffold_prefixes):
                    continue
                cleaned = WebUIChannel._strip_inline_scaffolding(text)
                if cleaned:
                    user_text_parts.append(cleaned)
        return "\n".join(user_text_parts), image_blocks

    @staticmethod
    def _strip_inline_scaffolding(text: str) -> str:
        """Excise math-contract preludes from a stored text payload.

        ``MathAgent.prepare_input`` glues the privacy math contract onto
        each math-turn user message; on rehydration we strip it back out
        so the bubble only renders the user's original prompt.
        """
        cleaned = _MATH_CONTRACT_PATTERN.sub("", text)
        return cleaned.strip()

    @staticmethod
    def _attachments_from_image_blocks(image_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Lift persisted image_url blocks into the frontend attachment shape.

        The persisted data URL is the *post-redaction* image (originals
        are never written to disk), so this is what the bubble will
        display in both local- and remote-view on history rehydration —
        consistent with the privacy contract ("the local original lives
        only in the original tab's memory").
        """
        attachments: list[dict[str, Any]] = []
        for block in image_blocks:
            image_url = block.get("image_url")
            url = None
            if isinstance(image_url, dict):
                url = image_url.get("url")
            if not isinstance(url, str) or not url.startswith("data:"):
                continue
            mime_type = url.split(";", 1)[0].removeprefix("data:") or "image/png"
            attachments.append({
                "mimeType": mime_type,
                "dataUrl": url,
            })
        return attachments

    @staticmethod
    def _attachment_results_from_payload(
        payload: WebUIPrivacyPayload | None,
    ) -> list[dict[str, Any]]:
        if payload is None:
            return []
        user_attachments = payload.privacy_turn.user_attachments
        if not user_attachments:
            return []
        return [
            attachment.model_dump(mode="json", by_alias=True)
            for attachment in user_attachments
        ]

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
        tool_approval = self._tool_approval_from_metadata(msg.metadata)
        await self._broadcast(
            msg.chat_id,
            WebUIAssistantMessageEvent(
                content=msg.content,
                tool_approval=tool_approval,
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
            if meta.get("_resuming"):
                return
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

    @staticmethod
    def _tool_approval_from_metadata(metadata: dict[str, object]) -> WebUIToolApproval | None:
        raw = metadata.get("tool_approval")
        if raw is None or raw is True:
            return None
        return WebUIChannel._validate_tool_approval(raw)

    @staticmethod
    def _tool_approval_from_message(message: dict[str, object]) -> WebUIToolApproval | None:
        return WebUIChannel._validate_tool_approval(message.get("tool_approval"))

    @staticmethod
    def _validate_tool_approval(raw: object) -> WebUIToolApproval | None:
        if not isinstance(raw, dict):
            return None
        try:
            return WebUIToolApproval.model_validate(raw)
        except ValidationError:
            logger.warning("webui: invalid tool approval payload skipped")
            return None

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
