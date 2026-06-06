from __future__ import annotations

import base64
import binascii
import mimetypes
import re
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
from cloakbot.privacy.core.state.vault import save_artifact_text
from cloakbot.privacy.document_redaction import process_user_document
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.protocol.contracts import EventType, PrivacyStage, ProtocolStatus
from cloakbot.privacy.protocol.observability import emit_event
from cloakbot.privacy.runtime.routing import normalize_intent, select_worker
from cloakbot.privacy.tool_models import ToolVaultArtifact
from cloakbot.privacy.transparency.report import TurnReport
from cloakbot.privacy.visual_redaction import process_visual_blocks
from cloakbot.utils.helpers import detect_image_mime

_PROMPT_VAULT_PREFIX = "user_input"
_DOCUMENT_VAULT_PREFIX = "user_document"

_DATA_URL_PATTERN = re.compile(
    r"data:(?P<mime>image/[-+.\w]+);base64,(?P<payload>.+)",
    flags=re.DOTALL,
)

# Document data URLs use a broader MIME pattern (``text/plain``,
# ``text/markdown`` today; reserved for future expansion to other
# text-shaped formats). The match-anything-text shape lets a single
# regex serve both the upload filter and the decoder.
_DOCUMENT_DATA_URL_PATTERN = re.compile(
    r"data:(?P<mime>text/[-+.\w]+);base64,(?P<payload>.+)",
    flags=re.DOTALL,
)
_SUPPORTED_DOCUMENT_MIMES = frozenset({"text/plain", "text/markdown"})
# Hard cap on uploaded document size at the privacy layer. Above this
# the document is dropped with a fail-closed notice — chunking
# 100k-char payloads would dominate latency and put us out of vLLM's
# practical recall envelope long before we get a useful signal.
_MAX_DOCUMENT_CHARS = 64_000


def _decode_data_url(reference: str) -> tuple[bytes, str | None] | None:
    """Parse a ``data:image/...;base64,...`` URL into ``(raw_bytes, mime)``.

    Returns ``None`` on any malformed prefix or invalid base64 — callers
    log a sanitized fingerprint rather than the raw URL so the failure
    path never echoes user content into the log stream.
    """
    match = _DATA_URL_PATTERN.fullmatch(reference)
    if not match:
        return None
    try:
        raw = base64.b64decode(match.group("payload"), validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw:
        return None
    return raw, match.group("mime")


def _document_suffix(mime: str) -> str:
    """File extension to use when persisting an uploaded document.

    Kept conservative — only the MIMEs that pass
    :data:`_SUPPORTED_DOCUMENT_MIMES` should reach here, and we want a
    short stable suffix per family so a glob over the vault can find
    "all user-uploaded contracts" without parsing every file.
    """
    return {"text/plain": "txt", "text/markdown": "md"}.get(mime, "txt")


def _media_fingerprint(reference: str) -> str:
    """Short, log-safe summary of a media reference.

    For inline data URLs we keep only the mime-prefix tag; for filesystem
    paths we keep the final path segment. The intent is "enough to debug
    a mis-routed upload, never enough to leak the underlying bytes."
    """
    if reference.startswith("data:"):
        head, _, _ = reference.partition(";")
        return f"<{head}…>"
    tail = reference.rsplit("/", 1)[-1]
    if len(tail) > 24:
        return f"<…{tail[-24:]}>"
    return f"<{tail}>"


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
            if _visual_privacy_enabled():
                image_blocks = await self._prepare_media(media, ctx)
            else:
                # [visual privacy — alpha] OFF (default): do NOT run the visual
                # redaction pipeline. Attach the RAW image blocks so the model sees
                # the image as-is (normal multimodal behaviour) — the user has
                # opted out of visual privacy for images. Typed text is still
                # placeholdered, and documents still go through the text pipeline.
                image_blocks = self._build_image_blocks_from_media(media) or None
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
        """Read media references into ``image_url`` blocks for visual processing.

        Accepts two reference shapes:

        - ``data:image/<mime>;base64,<payload>`` — inline data URLs sent by
          the WebUI/clipboard path. Parsed in-memory; the source ``path``
          metadata is suppressed because the original filename/contents
          have no on-disk anchor.
        - Filesystem paths (legacy channel uploads via Feishu/Slack/QQ).
          Read with the same constraints as
          ``agent.context.ContextBuilder._build_user_content``.

        Warning logs **never** print the raw reference: data URLs carry
        the user's raw image bytes in base64, and even fs paths can
        include sensitive folder names. We log a short fingerprint
        (kind + first 24 chars) so debugging stays useful without
        defeating the privacy boundary on its own log line.
        """
        blocks: list[dict[str, Any]] = []
        for reference in media:
            if not isinstance(reference, str) or not reference:
                continue

            if reference.startswith("data:"):
                # Text documents (``data:text/markdown;…``, ``data:text/plain;…``)
                # are handled by ``_prepare_user_documents`` via the chunker
                # pipeline. Silently skip them here so the image branch
                # doesn't warn on a non-image MIME it was never meant to
                # decode. The warning below is reserved for genuinely
                # malformed image data URLs.
                if _DOCUMENT_DATA_URL_PATTERN.fullmatch(reference):
                    continue
                raw_mime: tuple[bytes, str | None] | None = _decode_data_url(reference)
                if raw_mime is None:
                    logger.warning(
                        "cannot decode user-attached media: {} ({} chars)",
                        _media_fingerprint(reference),
                        len(reference),
                    )
                    continue
                raw, declared_mime = raw_mime
                mime = detect_image_mime(raw) or declared_mime
                if not mime or not mime.startswith("image/"):
                    continue
                b64 = base64.b64encode(raw).decode("ascii")
                blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                        # No on-disk path — WebUI uploads are session-scoped only.
                        "_meta": {"path": None},
                    }
                )
                continue

            try:
                p = Path(reference)
                if not p.is_file():
                    continue
                raw = p.read_bytes()
            except OSError as exc:
                logger.warning(
                    "cannot read user-attached media {}: {}",
                    _media_fingerprint(reference),
                    exc,
                )
                continue
            mime = detect_image_mime(raw) or mimetypes.guess_type(reference)[0]
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
        documents = self._extract_documents_from_media(media)
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
                    f"original_document.{_document_suffix(mime)}",
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

    @staticmethod
    def _extract_documents_from_media(
        media: list[str],
    ) -> list[tuple[str, str, str | None]]:
        """Decode ``data:text/...`` entries to ``(text, mime, name)`` tuples.

        Image data URLs and on-disk paths are skipped — the visual
        pipeline picks those up separately in
        :meth:`_build_image_blocks_from_media`. Anything that decodes
        but exceeds ``_MAX_DOCUMENT_CHARS`` is dropped with a sanitized
        log line; we don't want a 1MB paste to dominate latency.

        Document names are not part of the data URL spec — channels
        that want to surface a filename should encode it into the
        attachment metadata (``WebUIAttachment.name``) which is
        threaded separately. This helper returns ``None`` for the
        name slot and lets the caller fill it in if available.
        """
        out: list[tuple[str, str, str | None]] = []
        for reference in media:
            if not isinstance(reference, str) or not reference.startswith("data:"):
                continue
            match = _DOCUMENT_DATA_URL_PATTERN.fullmatch(reference)
            if not match:
                continue
            mime = match.group("mime")
            if mime not in _SUPPORTED_DOCUMENT_MIMES:
                continue
            try:
                raw = base64.b64decode(match.group("payload"), validate=True)
            except (binascii.Error, ValueError):
                logger.warning(
                    "cannot decode user-uploaded document: {} ({} chars)",
                    _media_fingerprint(reference),
                    len(reference),
                )
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(
                    "user-uploaded document is not valid UTF-8: {}",
                    _media_fingerprint(reference),
                )
                continue
            if len(text) > _MAX_DOCUMENT_CHARS:
                logger.warning(
                    "user-uploaded document exceeds the {} char privacy cap; "
                    "dropping ({} chars, mime={})",
                    _MAX_DOCUMENT_CHARS,
                    len(text),
                    mime,
                )
                continue
            out.append((text, mime, None))
        return out

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
