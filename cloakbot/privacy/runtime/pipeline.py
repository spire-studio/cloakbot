from __future__ import annotations

import base64
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from cloakbot.privacy.agents.classification.intent_analyzer import analyze_user_intent
from cloakbot.privacy.core.sanitization.restorer import build_local_computation_annotations
from cloakbot.privacy.core.sanitization.sanitize import (
    remap_response_with_annotations,
    sanitize_input_with_detection,
)
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.contracts import EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.observability import emit_event
from cloakbot.privacy.runtime.routing import normalize_intent, select_worker
from cloakbot.privacy.tool_models import ToolVaultArtifact
from cloakbot.privacy.transparency.report import TurnReport
from cloakbot.privacy.visual_redaction import process_visual_blocks
from cloakbot.utils.helpers import detect_image_mime

_PROMPT_VAULT_PREFIX = "user_input"


class PrivacyRuntime:
    def __init__(self, *, channel: str = "cli") -> None:
        self.channel = channel

    @staticmethod
    def _trace_id(ctx: TurnContext) -> str:
        return f"{ctx.session_key}:{ctx.turn_id}"

    @staticmethod
    def _span_id(ctx: TurnContext, stage: str) -> str:
        return f"{ctx.turn_id}:{stage}"

    async def prepare_turn(
        self,
        text: str,
        session_key: str,
        *,
        media: list[str] | None = None,
        fail_open: bool = True,
    ) -> tuple[str | list[dict[str, Any]], TurnContext]:
        ctx = TurnContext(session_key=session_key, turn_id=str(uuid.uuid4()), raw_input=text)
        trace_id = self._trace_id(ctx)

        emit_event(
            event_type=EventType.TURN_RECEIVED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "received"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.RAW,
            status=ProtocolStatus.STARTED,
            payload={"channel": self.channel},
        )
        emit_event(
            event_type=EventType.TURN_SANITIZE_STARTED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "sanitize"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.RAW,
            status=ProtocolStatus.STARTED,
            payload={"input_length": len(text)},
        )
        try:
            sanitized, modified, entities, _ = await sanitize_input_with_detection(
                text,
                session_key,
                fail_open=fail_open,
                turn_id=ctx.turn_id,
            )
        except Exception as exc:
            emit_event(
                event_type=EventType.TURN_SANITIZE_FAILED,
                trace_id=trace_id,
                span_id=f"{self._span_id(ctx, 'sanitize')}:failed",
                parent_span_id=self._span_id(ctx, "sanitize"),
                session_id=ctx.session_key,
                turn_id=ctx.turn_id,
                stage=PrivacyStage.RAW,
                status=ProtocolStatus.FAILED,
                payload={"error": str(exc)},
            )
            raise
        emit_event(
            event_type=EventType.TURN_SANITIZE_SUCCEEDED,
            trace_id=trace_id,
            span_id=f"{self._span_id(ctx, 'sanitize')}:completed",
            parent_span_id=self._span_id(ctx, "sanitize"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"was_sanitized": modified},
        )
        ctx.sanitized_input = sanitized
        ctx.was_sanitized = modified
        ctx.user_input_entities = entities

        analyzed_intent = await analyze_user_intent(text)
        ctx.intent = normalize_intent(analyzed_intent)
        emit_event(
            event_type=EventType.TURN_INTENT_CLASSIFIED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "intent"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.SUCCEEDED,
            payload={
                "analyzed_intent": analyzed_intent.value,
                "routed_intent": ctx.intent.value,
            },
        )

        emit_event(
            event_type=EventType.TURN_DISPATCH_STARTED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "dispatch"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.STARTED,
            payload={"intent": ctx.intent.value},
        )
        worker = select_worker(ctx.intent)
        try:
            prepared = await worker.prepare_input(ctx)
        except Exception as exc:
            emit_event(
                event_type=EventType.TURN_DISPATCH_FAILED,
                trace_id=trace_id,
                span_id=f"{self._span_id(ctx, 'dispatch')}:failed",
                parent_span_id=self._span_id(ctx, "dispatch"),
                session_id=ctx.session_key,
                turn_id=ctx.turn_id,
                stage=PrivacyStage.SANITIZED,
                status=ProtocolStatus.FAILED,
                payload={"error": str(exc), "intent": ctx.intent.value},
            )
            raise
        emit_event(
            event_type=EventType.TURN_DISPATCH_COMPLETED,
            trace_id=trace_id,
            span_id=f"{self._span_id(ctx, 'dispatch')}:completed",
            parent_span_id=self._span_id(ctx, "dispatch"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"intent": ctx.intent.value},
        )
        ctx.remote_prompt = prepared

        if media:
            media_blocks = await self._prepare_media(media, ctx)
            if media_blocks:
                prepared_content: list[dict[str, Any]] = [
                    *media_blocks,
                    {"type": "text", "text": prepared},
                ]
                return prepared_content, ctx

        return prepared, ctx

    async def _prepare_media(
        self,
        media: list[str],
        ctx: TurnContext,
    ) -> list[dict[str, Any]] | None:
        """Read user-attached files, run the visual privacy pipeline.

        Returns the (post-redaction or omit-placeholder) blocks to splice
        into the user message, or ``None`` when no usable image was
        produced. All visual records are stashed on the :class:`TurnContext`.
        """
        blocks = self._build_image_blocks_from_media(media)
        if not blocks:
            return None

        try:
            result = await process_visual_blocks(
                blocks,
                session_key=ctx.session_key,
                turn_id=ctx.turn_id,
                vault_call_id=f"{_PROMPT_VAULT_PREFIX}_{ctx.turn_id[:8]}",
            )
        except Exception as exc:
            logger.warning(
                "visual privacy pipeline failed for user input ({} attachments): {}",
                len(blocks),
                exc,
            )
            # Fail-closed at the outer boundary: drop the attachments and
            # add a notice so the user-visible turn proceeds without leaks.
            return [
                {
                    "type": "text",
                    "text": (
                        "[visual content omitted; visual privacy pipeline unavailable: "
                        f"{type(exc).__name__}]"
                    ),
                }
            ]

        if result.entities:
            ctx.user_input_entities.extend(result.entities)
        if result.visual_redactions:
            ctx.user_input_visual_redactions.extend(result.visual_redactions)
        if result.vault_entries:
            ctx.user_input_vault_artifacts.extend(
                ToolVaultArtifact(
                    kind=entry.kind,
                    path=entry.path,
                    mediaType=entry.media_type,
                )
                for entry in result.vault_entries
            )
        ctx.user_input_media_blocks = list(result.redacted_blocks)
        if result.modified:
            ctx.was_sanitized = True

        prepared_blocks: list[dict[str, Any]] = list(result.redacted_blocks)
        if result.omitted_count > 0 and result.sanitized_text:
            prepared_blocks.append(
                {
                    "type": "text",
                    "text": (
                        "[Local OCR transcript of omitted attachments — already "
                        "privacy-sanitized; treat as supplemental context]:\n"
                        + result.sanitized_text
                    ),
                }
            )
        return prepared_blocks

    @staticmethod
    def _build_image_blocks_from_media(media: list[str]) -> list[dict[str, Any]]:
        """Read media paths into ``image_url`` blocks for visual processing.

        Mirrors ``agent.context.ContextBuilder._build_user_content`` but
        keeps the path on ``_meta`` so visual redaction records can cite
        the source for transparency without leaking it to the LLM.
        """
        blocks: list[dict[str, Any]] = []
        for path in media:
            try:
                p = Path(path)
                if not p.is_file():
                    continue
                raw = p.read_bytes()
            except OSError as exc:
                logger.warning("cannot read user-attached media {}: {}", path, exc)
                continue
            mime = detect_image_mime(raw) or mimetypes.guess_type(path)[0]
            if not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(raw).decode("ascii")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                    "_meta": {"path": str(p)},
                }
            )
        return blocks

    async def finalize_turn(self, response: str, ctx: TurnContext, *, include_report: bool = True) -> str:
        trace_id = self._trace_id(ctx)

        emit_event(
            event_type=EventType.TURN_RESTORE_STARTED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "restore"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.STARTED,
            payload={"response_length": len(response)},
        )

        worker = select_worker(ctx.intent)
        try:
            finalized = await worker.finalize_output(response, ctx)
            ctx.sanitized_output = finalized

            restored, annotations = await remap_response_with_annotations(finalized, ctx.session_key)
            annotations.extend(build_local_computation_annotations(restored, ctx.local_computations))
            annotations.sort(key=lambda annotation: (annotation.start, annotation.end))
            ctx.display_output = restored
            ctx.display_output_annotations = annotations
        except Exception as exc:
            emit_event(
                event_type=EventType.TURN_RESTORE_FAILED,
                trace_id=trace_id,
                span_id=f"{self._span_id(ctx, 'restore')}:failed",
                parent_span_id=self._span_id(ctx, "restore"),
                session_id=ctx.session_key,
                turn_id=ctx.turn_id,
                stage=PrivacyStage.SANITIZED,
                status=ProtocolStatus.FAILED,
                payload={"error": str(exc)},
            )
            raise

        emit_event(
            event_type=EventType.TURN_RESTORE_COMPLETED,
            trace_id=trace_id,
            span_id=f"{self._span_id(ctx, 'restore')}:completed",
            parent_span_id=self._span_id(ctx, "restore"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.POSTPROCESSED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"annotation_count": len(annotations)},
        )

        report_text = TurnReport(ctx=ctx).render()
        if include_report and report_text:
            restored = f"{restored}\n\n{report_text}"

        emit_event(
            event_type=EventType.TURN_COMPLETED,
            trace_id=trace_id,
            span_id=self._span_id(ctx, "completed"),
            parent_span_id=self._span_id(ctx, "received"),
            session_id=ctx.session_key,
            turn_id=ctx.turn_id,
            stage=PrivacyStage.POSTPROCESSED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"include_report": include_report},
        )
        return restored


_RUNTIME = PrivacyRuntime(channel="cli")


def get_runtime() -> PrivacyRuntime:
    return _RUNTIME
