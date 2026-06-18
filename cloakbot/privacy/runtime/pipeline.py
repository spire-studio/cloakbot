from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from typing import Any

from loguru import logger

from cloakbot.privacy.agents.classification.intent_analyzer import analyze_user_intent
from cloakbot.privacy.core.sanitization.restorer import build_local_computation_annotations
from cloakbot.privacy.core.sanitization.sanitize import (
    remap_response_with_annotations,
    sanitize_input_with_detection,
)
from cloakbot.privacy.core.state.vault import save_artifact_text
from cloakbot.privacy.document_redaction import process_user_document
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.contracts import EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.observability import emit_event
from cloakbot.privacy.runtime.attachments import (
    build_image_blocks_from_media,
    document_suffix,
    extract_documents_from_media,
)
from cloakbot.privacy.runtime.routing import normalize_intent, select_worker
from cloakbot.privacy.tool_models import ToolVaultArtifact
from cloakbot.privacy.transparency.report import TurnReport
from cloakbot.privacy.visual_redaction import process_visual_blocks

_PROMPT_VAULT_PREFIX = "user_input"
_DOCUMENT_VAULT_PREFIX = "user_document"


def _visual_privacy_enabled() -> bool:
    """Whether the alpha visual-redaction pipeline is enabled (config; default OFF).

    ON: uploaded images are run through local visual redaction before the model
    sees them. OFF (default): images are sent to the model as-is (no redaction) —
    the user has opted out of visual privacy for images. Read fresh (only on media
    turns) so a Settings toggle applies to the next message without a gateway
    restart. Any failure — no config file, parse error — resolves to the OFF
    default.
    """
    try:
        from cloakbot.config.loader import get_config_path, load_config

        if not get_config_path().exists():
            return False
        return bool(load_config().privacy.visual_enabled)
    except Exception:
        return False


def privacy_mode_active() -> bool:
    """Master switch for the whole privacy pipeline (config ``privacy.enabled``).

    When this returns False the loop bypasses sanitization/restoration entirely —
    raw text and images reach the model, like a plain assistant. Defaults to
    ACTIVE (True) whenever the config is unreadable (fresh install, tests, parse
    error) so privacy is NEVER silently disabled; only an explicit
    ``privacy.enabled = false`` bypasses it. (Whether privacy is *effectively* on
    also depends on a detector being configured — that gating is surfaced to the
    UI via the settings ``active`` flag, while the pipeline itself fail-opens with
    no detector.)
    """
    try:
        from cloakbot.config.loader import get_config_path, load_config

        if not get_config_path().exists():
            return True
        return bool(load_config().privacy.enabled)
    except Exception:
        return True


class _TurnObservability:
    """Per-turn observability emitter.

    Binds the trace/session/turn identity once and brackets each pipeline
    stage's STARTED → SUCCEEDED / FAILED triple into a single ``with`` block, so
    the stage body stays readable and the three events can't drift out of sync.
    """

    def __init__(self, ctx: TurnContext, *, channel: str) -> None:
        self._ctx = ctx
        self.channel = channel
        self._trace_id = f"{ctx.session_key}:{ctx.turn_id}"

    def emit(
        self,
        event_type: EventType,
        *,
        span: str,
        stage: PrivacyStage,
        status: ProtocolStatus,
        payload: dict[str, Any],
        parent: str | None = None,
    ) -> None:
        emit_event(
            event_type=event_type,
            trace_id=self._trace_id,
            span_id=f"{self._ctx.turn_id}:{span}",
            parent_span_id=f"{self._ctx.turn_id}:{parent}" if parent is not None else None,
            session_id=self._ctx.session_key,
            turn_id=self._ctx.turn_id,
            stage=stage,
            status=status,
            payload=payload,
        )

    @contextlib.contextmanager
    def span(
        self,
        name: str,
        *,
        events: tuple[EventType, EventType, EventType],
        start_stage: PrivacyStage,
        end_stage: PrivacyStage,
        start_payload: dict[str, Any],
        error_payload: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Emit STARTED, run the body, then emit SUCCEEDED (or FAILED on raise).

        ``events`` is the ``(started, succeeded, failed)`` event-type triple.
        Yields a mutable dict the body fills in as the success payload.
        """
        started, succeeded, failed = events
        self.emit(started, span=name, stage=start_stage, status=ProtocolStatus.STARTED, payload=start_payload)
        end_payload: dict[str, Any] = {}
        try:
            yield end_payload
        except Exception as exc:
            self.emit(
                failed,
                span=f"{name}:failed",
                parent=name,
                stage=start_stage,
                status=ProtocolStatus.FAILED,
                payload={"error": str(exc), **(error_payload or {})},
            )
            raise
        self.emit(
            succeeded,
            span=f"{name}:completed",
            parent=name,
            stage=end_stage,
            status=ProtocolStatus.SUCCEEDED,
            payload=end_payload,
        )


class PrivacyRuntime:
    def __init__(self, *, channel: str = "cli") -> None:
        self.channel = channel

    async def prepare_turn(
        self,
        text: str,
        session_key: str,
        *,
        media: list[str] | None = None,
        fail_open: bool = True,
    ) -> tuple[str | list[dict[str, Any]], TurnContext]:
        ctx = TurnContext(session_key=session_key, turn_id=str(uuid.uuid4()), raw_input=text)
        obs = _TurnObservability(ctx, channel=self.channel)

        obs.emit(
            EventType.TURN_RECEIVED,
            span="received",
            stage=PrivacyStage.RAW,
            status=ProtocolStatus.STARTED,
            payload={"channel": self.channel},
        )

        with obs.span(
            "sanitize",
            events=(
                EventType.TURN_SANITIZE_STARTED,
                EventType.TURN_SANITIZE_SUCCEEDED,
                EventType.TURN_SANITIZE_FAILED,
            ),
            start_stage=PrivacyStage.RAW,
            end_stage=PrivacyStage.SANITIZED,
            start_payload={"input_length": len(text)},
        ) as sanitize_done:
            sanitized, modified, entities, _ = await sanitize_input_with_detection(
                text,
                session_key,
                fail_open=fail_open,
                turn_id=ctx.turn_id,
            )
            sanitize_done["was_sanitized"] = modified
        ctx.sanitized_input = sanitized
        ctx.was_sanitized = modified
        ctx.user_input_entities = entities

        analyzed_intent = await analyze_user_intent(text)
        ctx.intent = normalize_intent(analyzed_intent)
        obs.emit(
            EventType.TURN_INTENT_CLASSIFIED,
            span="intent",
            stage=PrivacyStage.SANITIZED,
            status=ProtocolStatus.SUCCEEDED,
            payload={
                "analyzed_intent": analyzed_intent.value,
                "routed_intent": ctx.intent.value,
            },
        )

        with obs.span(
            "dispatch",
            events=(
                EventType.TURN_DISPATCH_STARTED,
                EventType.TURN_DISPATCH_COMPLETED,
                EventType.TURN_DISPATCH_FAILED,
            ),
            start_stage=PrivacyStage.SANITIZED,
            end_stage=PrivacyStage.SANITIZED,
            start_payload={"intent": ctx.intent.value},
            error_payload={"intent": ctx.intent.value},
        ) as dispatch_done:
            worker = select_worker(ctx.intent)
            prepared = await worker.prepare_input(ctx)
            dispatch_done["intent"] = ctx.intent.value
        ctx.remote_prompt = prepared

        if media:
            if _visual_privacy_enabled():
                image_blocks = await self._prepare_media(media, ctx)
            else:
                # [visual privacy — alpha] OFF (default): do NOT run the visual
                # redaction pipeline. Attach the RAW image blocks so the model sees
                # the image as-is (normal multimodal behaviour) — the user has
                # opted out of visual privacy for images. Typed text is still
                # placeholdered, and documents still go through the text pipeline.
                image_blocks = build_image_blocks_from_media(media) or None
            document_blocks = await self._prepare_user_documents(media, ctx)
            if image_blocks or document_blocks:
                # LLM-facing layout: images first (multimodal convention),
                # then the user's typed prompt, then any sanitized
                # document context. Documents go LAST so the LLM reads
                # the prompt before the supplemental long text.
                prepared_content: list[dict[str, Any]] = []
                if image_blocks:
                    prepared_content.extend(image_blocks)
                prepared_content.append({"type": "text", "text": prepared})
                if document_blocks:
                    prepared_content.extend(document_blocks)
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
        blocks = build_image_blocks_from_media(media)
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

    async def _prepare_user_documents(
        self,
        media: list[str],
        ctx: TurnContext,
    ) -> list[dict[str, Any]]:
        """Run chunker-backed PII detection on uploaded text documents.

        Sibling of :meth:`_prepare_media` (which handles image uploads).
        For every ``data:text/...;base64,...`` entry in ``media``, the
        document is decoded, persisted as a vault artifact (original
        bytes), and routed through ``process_user_document`` which in
        turn delegates to ``sanitize_tool_output_chunked`` — the same
        chunker code path A3 measures end-to-end. Sanitized text is
        emitted as a ``text`` content block tagged with the document
        name so the LLM sees it as supplemental context rather than
        primary input.

        Failures fail closed: a document whose decoding or sanitisation
        raises is replaced with an omit notice block, and no original
        text reaches the LLM-bound payload.
        """
        documents = extract_documents_from_media(media)
        if not documents:
            return []

        prepared: list[dict[str, Any]] = []
        for index, (text, mime, name) in enumerate(documents):
            label = name or f"document_{index + 1}"
            vault_call_id = f"{_DOCUMENT_VAULT_PREFIX}_{ctx.turn_id[:8]}_{index}"

            # Persist the original text to the per-session vault BEFORE
            # sanitisation so a reload (and the WebUI Local-view) can
            # recover the user's true upload without re-reading from
            # the browser. The redacted text is reconstructible from
            # the session vault on demand, so we don't double-write it.
            try:
                original_path = save_artifact_text(
                    ctx.session_key,
                    ctx.turn_id,
                    vault_call_id,
                    f"original_document.{document_suffix(mime)}",
                    text,
                )
                ctx.user_input_document_artifacts.append(
                    ToolVaultArtifact(
                        kind="original_document",
                        path=str(original_path),
                        mediaType=mime,
                    )
                )
            except OSError as exc:
                logger.warning(
                    "cannot persist user-uploaded document to vault ({}): {}",
                    label,
                    exc,
                )

            try:
                result = await process_user_document(
                    text,
                    session_key=ctx.session_key,
                    turn_id=ctx.turn_id,
                    document_name=name,
                    mime_type=mime,
                )
            except Exception as exc:
                logger.warning(
                    "document privacy pipeline failed for upload {}: {}",
                    label,
                    exc,
                )
                prepared.append(
                    {
                        "type": "text",
                        "text": (
                            f"[document upload `{label}` omitted; "
                            f"privacy pipeline unavailable: "
                            f"{type(exc).__name__}]"
                        ),
                    }
                )
                continue

            ctx.user_input_documents.append(result)
            if result.was_sanitized:
                ctx.was_sanitized = True

            header = (
                f"[Document uploaded by user: `{label}` — privacy-sanitized; "
                f"treat as supplemental context. "
                f"Chunks: {result.chunks_total}"
                + (", with at least one chunk-local detection failure" if result.chunks_failed else "")
                + "]"
            )
            prepared.append(
                {
                    "type": "text",
                    "text": header + "\n" + result.sanitized_text,
                }
            )

        return prepared

    async def finalize_turn(self, response: str, ctx: TurnContext, *, include_report: bool = True) -> str:
        obs = _TurnObservability(ctx, channel=self.channel)

        with obs.span(
            "restore",
            events=(
                EventType.TURN_RESTORE_STARTED,
                EventType.TURN_RESTORE_COMPLETED,
                EventType.TURN_RESTORE_FAILED,
            ),
            start_stage=PrivacyStage.SANITIZED,
            end_stage=PrivacyStage.POSTPROCESSED,
            start_payload={"response_length": len(response)},
        ) as restore_done:
            worker = select_worker(ctx.intent)
            finalized = await worker.finalize_output(response, ctx)
            ctx.sanitized_output = finalized

            restored, annotations = await remap_response_with_annotations(finalized, ctx.session_key)
            annotations.extend(build_local_computation_annotations(restored, ctx.local_computations))
            annotations.sort(key=lambda annotation: (annotation.start, annotation.end))
            ctx.display_output = restored
            ctx.display_output_annotations = annotations
            restore_done["annotation_count"] = len(annotations)

        report_text = TurnReport(ctx=ctx).render()
        if include_report and report_text:
            restored = f"{restored}\n\n{report_text}"

        obs.emit(
            EventType.TURN_COMPLETED,
            span="completed",
            parent="received",
            stage=PrivacyStage.POSTPROCESSED,
            status=ProtocolStatus.SUCCEEDED,
            payload={"include_report": include_report},
        )
        return restored


_RUNTIME = PrivacyRuntime(channel="cli")


def get_runtime() -> PrivacyRuntime:
    return _RUNTIME
