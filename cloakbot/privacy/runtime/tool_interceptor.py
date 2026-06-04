from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from cloakbot.privacy.core.detection.chunking import DEFAULT_MAX_CHARS
from cloakbot.privacy.core.sanitization.sanitize import (
    remap_response,
    sanitize_tool_output,
    sanitize_tool_output_chunked,
)
from cloakbot.privacy.core.state.vault import (
    PLACEHOLDER_RE,
    save_artifact_text,
)
from cloakbot.privacy.core.types import Severity
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.runtime.streaming_sanitizer import StreamingSanitizerRegistry
from cloakbot.privacy.tool_models import (
    ToolApprovalRequest,
    ToolApprovalRequiredError,
    ToolPrivacyClass,
    ToolPrivacyRecord,
    ToolVaultArtifact,
)
from cloakbot.privacy.visual_redaction import (
    VisualPrivacyRedaction,
    is_visual_content_blocks,
    process_visual_blocks,
)
from cloakbot.providers.base import ToolCallRequest
from cloakbot.utils.helpers import stringify_text_blocks

# Strings shorter than this stay on the single-shot detector path —
# the chunker would produce one chunk and just add overhead. Crossing
# the threshold unlocks chunked, concurrent detection with per-chunk
# fail-closed signalling.
_CHUNK_ROUTING_THRESHOLD = DEFAULT_MAX_CHARS

# Strict-mode escape hatch: when set, ``LOCAL`` tool calls whose
# restored arguments contain a Severity.HIGH entity (SSN, credential,
# medical, etc.) still raise :class:`ToolApprovalRequiredError`. Off by
# default so the existing user-experience isn't disturbed; orgs that
# want a hard wall around sensitive locals opt in via env.
_HIGH_SEVERITY_LOCAL_ENV = "CLOAKBOT_APPROVAL_HIGH_SEVERITY_LOCAL"


def _high_severity_local_required() -> bool:
    return os.getenv(_HIGH_SEVERITY_LOCAL_ENV, "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _has_high_severity(entities: list[Any]) -> bool:
    return any(getattr(e, "severity", None) is Severity.HIGH for e in entities)


_MAX_RECORDED_OUTPUT_CHARS = 4000

# Tools whose text output arrives incrementally across multiple poll/write
# calls against the same long-running stream (exec sessions, shell, long_task
# progress). Their results are routed through the per-stream
# :class:`StreamingSanitizer` so an entity straddling a poll boundary is still
# detected as one unit and never leaks raw across the seam (Cap A).
_STREAMING_TOOLS: frozenset[str] = frozenset(
    {
        "exec",
        "write_stdin",
        "shell",
        "long_task",
    }
)


# Terminal markers emitted by ``format_session_poll`` (exec_session.py) when the
# underlying process has finished. Presence of any of these means no further
# bytes will arrive on this stream, so the carry-over tail can be flushed.
_STREAM_DONE_MARKERS: tuple[str, ...] = (
    "Exit code:",
    "Session terminated.",
    "Command timed out; session was terminated.",
)
# The non-terminal marker: while present, the exec stream is still live and the
# carry-over tail must be withheld for the next poll.
_STREAM_RUNNING_MARKER = "Process running. session_id:"


def _stream_is_live(result: str) -> bool:
    """True when more bytes are still expected on this stream.

    Only an exec-session poll that printed the "Process running" marker (and no
    terminal marker) is treated as live; everything else is finalized at the end
    of the current call so no settled output is withheld from the model.
    """
    if any(marker in result for marker in _STREAM_DONE_MARKERS):
        return False
    return _STREAM_RUNNING_MARKER in result


# Status-trailer lines appended by ``format_session_poll`` after the process
# output. They are generated locally and contain no user PII, so we split them
# off, sanitize only the *output* region through the carry-over window, and
# re-append the trailer verbatim. This keeps a status line from ever splitting
# an entity across the held-back boundary.
_TRAILER_LINE_PREFIXES: tuple[str, ...] = (
    "(output truncated by ",
    "Error: Command timed out; session was terminated.",
    "Session terminated.",
    "Stdin closed.",
    "Exit code:",
    "Process running. session_id:",
    "Elapsed:",
)


def _split_session_output_and_trailer(result: str) -> tuple[str, str]:
    """Split a formatted exec poll into ``(process_output, status_trailer)``.

    The trailer is the maximal suffix of whole lines that are all recognized
    status lines. Everything before it is the process's own output, which is the
    only part that may carry PII and the only part fed through the stream.
    """
    lines = result.split("\n")
    cut = len(lines)
    for idx in range(len(lines) - 1, -1, -1):
        if any(lines[idx].startswith(prefix) for prefix in _TRAILER_LINE_PREFIXES):
            cut = idx
        else:
            break
    if cut >= len(lines):
        return result, ""
    output = "\n".join(lines[:cut])
    trailer = "\n".join(lines[cut:])
    return output, trailer


def _join_output_trailer(output: str, trailer: str) -> str:
    """Recombine sanitized output with its status trailer."""
    if not trailer:
        return output
    if not output:
        return trailer
    return output + "\n" + trailer


def _stream_id_for(tool_call: ToolCallRequest) -> str | None:
    """Stable per-stream key for a streaming tool call.

    Exec-session polls all carry the same ``session_id`` argument, which is the
    only identity stable across the successive ``write_stdin`` polls of one
    stream. Falls back to the (per-call, unstable) ``tool_call.id`` so a tool we
    have flagged streaming but that lacks a session arg still gets carry-over
    within a single call's finalize bracket.
    """
    args = tool_call.arguments
    if isinstance(args, dict):
        for key in ("session_id", "stream_id", "task_id", "goal_id"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return f"{tool_call.name}:{value.strip()}"
    return f"{tool_call.name}:{tool_call.id}" if tool_call.id else None


class ToolPrivacyInterceptor:
    """Restore local tool inputs and sanitize tool outputs before model reuse."""

    def __init__(self, ctx: TurnContext) -> None:
        self._ctx = ctx
        self._follow_up_messages: dict[str, list[dict[str, Any]]] = {}
        # Per-(session_key, stream_id) carry-over windows for streaming tools.
        self._stream_registry = StreamingSanitizerRegistry()

    async def prepare_tool_call(
        self,
        tool_call: ToolCallRequest,
        *,
        privacy_class: ToolPrivacyClass,
    ) -> ToolCallRequest:
        restored_arguments = await self._restore_value(tool_call.arguments)
        local_file_call = _local_file_read_rewrite(tool_call, restored_arguments)
        if local_file_call is not None:
            return local_file_call

        if privacy_class is not ToolPrivacyClass.LOCAL:
            (
                sanitized_arguments,
                modified,
                entities,
                _visual_redactions,
                _failed,
            ) = await self._sanitize_value(restored_arguments)
            placeholder_sensitive = _contains_placeholder(tool_call.arguments)
            sensitive = modified or placeholder_sensitive
            if sensitive:
                self._ctx.tool_input_entities.extend(entities)
                request = ToolApprovalRequest(
                    approval_id=uuid4().hex,
                    session_key=self._ctx.session_key,
                    turn_id=self._ctx.turn_id,
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    privacy_class=privacy_class,
                    remote_arguments=_dict_or_empty(sanitized_arguments),
                    restored_arguments=_dict_or_empty(restored_arguments),
                    detected_entities=entities,
                )
                self._ctx.tool_approvals.append(request)
                raise ToolApprovalRequiredError(request)
        elif _high_severity_local_required():
            # Severity-driven approval gate for LOCAL tools. Opt-in so
            # the default user experience is unchanged. We compute
            # entities purely to inspect their severity; the returned
            # arguments stay the *restored* originals because LOCAL
            # tools execute on real values by design.
            (
                _sanitized_args,
                _modified,
                local_entities,
                _vr,
                _failed,
            ) = await self._sanitize_value(restored_arguments)
            if _has_high_severity(local_entities):
                self._ctx.tool_input_entities.extend(local_entities)
                request = ToolApprovalRequest(
                    approval_id=uuid4().hex,
                    session_key=self._ctx.session_key,
                    turn_id=self._ctx.turn_id,
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    privacy_class=privacy_class,
                    remote_arguments=_dict_or_empty(restored_arguments),
                    restored_arguments=_dict_or_empty(restored_arguments),
                    detected_entities=local_entities,
                )
                self._ctx.tool_approvals.append(request)
                raise ToolApprovalRequiredError(request)

        return ToolCallRequest(
            id=tool_call.id,
            name=tool_call.name,
            arguments=restored_arguments,
            extra_content=tool_call.extra_content,
            provider_specific_fields=tool_call.provider_specific_fields,
            function_provider_specific_fields=tool_call.function_provider_specific_fields,
        )

    async def sanitize_tool_result(
        self,
        tool_call: ToolCallRequest,
        result: Any,
        *,
        privacy_class: ToolPrivacyClass = ToolPrivacyClass.LOCAL,
    ) -> Any:
        if tool_call.name in _STREAMING_TOOLS and isinstance(result, str):
            return await self._sanitize_streaming_tool_result(
                tool_call,
                result,
                privacy_class=privacy_class,
            )

        vault_artifacts: list[ToolVaultArtifact] = []
        detection_failed = False
        if is_visual_content_blocks(result):
            sanitized, modified, entities, visual_redactions, vault_artifacts = await self._sanitize_visual_tool_result(
                tool_call,
                result,
            )
        else:
            (
                sanitized,
                modified,
                entities,
                visual_redactions,
                detection_failed,
            ) = await self._sanitize_value(result, tool_name=tool_call.name)
            vault_artifacts = self._persist_read_file_text_artifacts(tool_call, sanitized)

        if detection_failed:
            # Fail-closed: at least one chunk's local detector errored
            # or timed out. We cannot trust the partial entity list, so
            # replace the payload with a placeholder. The detected
            # entities so far still get recorded for transparency.
            sanitized = (
                f"[tool output omitted; privacy detection failed on one or more "
                f"chunks for tool {tool_call.name!r}]"
            )
            modified = True

        self._ctx.tool_output_entities.extend(entities)
        self._ctx.tool_results.append(
            ToolPrivacyRecord(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                privacy_class=privacy_class,
                remote_arguments=dict(tool_call.arguments),
                sanitized_output=_recorded_output_text(sanitized),
                was_sanitized=modified,
                visual_redactions=visual_redactions,
                vaultArtifacts=vault_artifacts,
            )
        )
        return sanitized

    async def _sanitize_streaming_tool_result(
        self,
        tool_call: ToolCallRequest,
        result: str,
        *,
        privacy_class: ToolPrivacyClass,
    ) -> str:
        """Sanitize one poll of a streaming tool through its carry-over window.

        Each poll's text is appended to the per-stream
        :class:`StreamingSanitizer`; we emit only the **settled** portion (output
        far enough behind the live tail that no future byte can extend an entity
        into it). The residual tail is held back only for a still-running
        ``write_stdin`` poll whose continuation reuses the same stream key; every
        other call finalizes immediately, flushing and sanitizing the tail. This
        guarantees an entity that straddles a poll boundary is detected as one
        contiguous unit and tokenized once,
        never partially emitted as raw characters.
        """
        stream_id = _stream_id_for(tool_call)
        # Separate the process output (may carry PII) from the locally-generated
        # status trailer (no PII). Only the output flows through the carry-over
        # window; the trailer is re-appended verbatim so a status line can never
        # split an entity across the held-back boundary.
        output, trailer = _split_session_output_and_trailer(result)

        if stream_id is None:
            # No stable stream identity: fall back to one-shot sanitization so we
            # still never feed raw output to the model.
            sanitized, modified, entities = await sanitize_tool_output(
                output,
                self._ctx.session_key,
                turn_id=self._ctx.turn_id,
            )
            final = _join_output_trailer(sanitized, trailer)
            self._record_streaming_result(tool_call, final, modified, entities, privacy_class)
            return final

        sanitizer = self._stream_registry.get(
            self._ctx.session_key,
            stream_id,
            turn_id=self._ctx.turn_id,
        )
        emitted = await sanitizer.feed(output)
        # Hold the carry-over tail back ONLY for a ``write_stdin`` poll whose
        # continuation will arrive under the SAME stream key (same ``session_id``)
        # and that is provably still live ("Process running"). ``exec`` is keyed
        # on its call id, so its continuation arrives as a *separate*
        # ``write_stdin`` stream — there is no same-key follow-up to flush its
        # tail, so we finalize it per call. Finished / terminated / timed-out
        # streams and single-call tools (``long_task``) also finalize now, so
        # nothing is ever withheld from the model indefinitely.
        hold_tail = tool_call.name == "write_stdin" and _stream_is_live(result)
        if not hold_tail:
            emitted += await self._stream_registry.finalize_stream(
                self._ctx.session_key,
                stream_id,
            )
        final = _join_output_trailer(emitted, trailer)
        self._record_streaming_result(
            tool_call,
            final,
            sanitizer.modified,
            sanitizer.entities,
            privacy_class,
        )
        return final

    def _record_streaming_result(
        self,
        tool_call: ToolCallRequest,
        sanitized: str,
        modified: bool,
        entities: list[Any],
        privacy_class: ToolPrivacyClass,
    ) -> None:
        self._ctx.tool_output_entities.extend(entities)
        self._ctx.tool_results.append(
            ToolPrivacyRecord(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                privacy_class=privacy_class,
                remote_arguments=dict(tool_call.arguments),
                sanitized_output=_recorded_output_text(sanitized),
                was_sanitized=modified,
                visual_redactions=[],
                vaultArtifacts=[],
            )
        )

    def finalize_streams(self) -> None:
        """Drop any still-open stream buffers (turn teardown)."""
        self._stream_registry.clear()

    def take_follow_up_messages(self, tool_call_id: str) -> list[dict[str, Any]]:
        return self._follow_up_messages.pop(tool_call_id, [])

    async def _restore_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return await remap_response(value, self._ctx.session_key)
        if isinstance(value, list):
            return [await self._restore_value(item) for item in value]
        if isinstance(value, dict):
            return {key: await self._restore_value(item) for key, item in value.items()}
        return value

    async def _sanitize_value(
        self,
        value: Any,
        *,
        tool_name: str | None = None,
    ) -> tuple[Any, bool, list[Any], list[VisualPrivacyRedaction], bool]:
        """Recursively sanitize a tool argument or result value.

        When ``tool_name`` is set, string leaves are routed through the
        chunked tool detector (``sanitize_tool_output_chunked``) and the
        fifth return element propagates a *detection_failed* signal so
        the caller can fail-closed on the whole payload. When
        ``tool_name`` is ``None`` (input-args path), the existing
        single-shot detector is used and the failure signal is always
        ``False``.
        """
        if isinstance(value, str):
            # Skip detection on strings that are entirely placeholders +
            # whitespace. Running PII detection on already-tokenized content
            # is wasted compute, and (worse) can produce nested or
            # mis-aligned tokens when a regex matches inside ``<<…_N>>``.
            if _is_pure_placeholder_text(value):
                return value, False, [], [], False
            if tool_name is not None and len(value) > _CHUNK_ROUTING_THRESHOLD:
                sanitized, modified, entities, failed = await sanitize_tool_output_chunked(
                    value,
                    self._ctx.session_key,
                    tool_name=tool_name,
                    turn_id=self._ctx.turn_id,
                )
                return sanitized, modified, entities, [], failed
            sanitized, modified, entities = await sanitize_tool_output(
                value,
                self._ctx.session_key,
                turn_id=self._ctx.turn_id,
            )
            return sanitized, modified, entities, [], False

        if isinstance(value, list):
            sanitized_items: list[Any] = []
            modified_any = False
            all_entities: list[Any] = []
            visual_redactions: list[VisualPrivacyRedaction] = []
            failed_any = False
            for item in value:
                (
                    sanitized_item,
                    modified,
                    entities,
                    item_visual_redactions,
                    failed,
                ) = await self._sanitize_value(item, tool_name=tool_name)
                sanitized_items.append(sanitized_item)
                modified_any = modified_any or modified
                all_entities.extend(entities)
                visual_redactions.extend(item_visual_redactions)
                failed_any = failed_any or failed
            return sanitized_items, modified_any, all_entities, visual_redactions, failed_any

        if isinstance(value, dict):
            sanitized_dict: dict[str, Any] = {}
            modified_any = False
            all_entities: list[Any] = []
            visual_redactions: list[VisualPrivacyRedaction] = []
            failed_any = False
            for key, item in value.items():
                (
                    sanitized_item,
                    modified,
                    entities,
                    item_visual_redactions,
                    failed,
                ) = await self._sanitize_value(item, tool_name=tool_name)
                sanitized_dict[key] = sanitized_item
                modified_any = modified_any or modified
                all_entities.extend(entities)
                visual_redactions.extend(item_visual_redactions)
                failed_any = failed_any or failed
            return sanitized_dict, modified_any, all_entities, visual_redactions, failed_any

        return value, False, [], [], False

    async def _sanitize_visual_tool_result(
        self,
        tool_call: ToolCallRequest,
        blocks: list[Any],
    ) -> tuple[Any, bool, list[Any], list[VisualPrivacyRedaction], list[ToolVaultArtifact]]:
        result = await process_visual_blocks(
            blocks,
            session_key=self._ctx.session_key,
            turn_id=self._ctx.turn_id,
            vault_call_id=tool_call.id,
            # OCR text persistence is handled per-tool by
            # ``_persist_read_file_text_artifacts`` below (read_file only),
            # so suppress the generic OCR artifact here to avoid duplicates.
            persist_ocr_text=False,
        )

        # Tool-result path: substitute the OCR text (or a safe fallback) as
        # the tool message content so the assistant can still cite the file
        # by name even when every image was omitted.
        sanitized_text = result.sanitized_text
        if not sanitized_text:
            fallback = stringify_text_blocks(result.redacted_blocks)
            sanitized_text = fallback or "[visual content available locally, but no OCR text was extracted]"

        vault_artifacts: list[ToolVaultArtifact] = [
            ToolVaultArtifact(
                kind=entry.kind,
                path=entry.path,
                mediaType=entry.media_type,
            )
            for entry in result.vault_entries
        ]
        vault_artifacts.extend(self._persist_read_file_text_artifacts(tool_call, sanitized_text))

        redacted_image_entry = next(
            (entry for entry in result.vault_entries if entry.kind == "redacted_image"),
            None,
        )
        if redacted_image_entry is not None:
            self._follow_up_messages[tool_call.id] = [
                _build_visual_follow_up_message(
                    redacted_image_entry.path,
                    redacted_image_entry.media_type or "image/png",
                    tool_call.id,
                )
            ]

        return (
            sanitized_text,
            result.modified,
            result.entities,
            result.visual_redactions,
            vault_artifacts,
        )

    def _persist_read_file_text_artifacts(
        self,
        tool_call: ToolCallRequest,
        sanitized: Any,
    ) -> list[ToolVaultArtifact]:
        if tool_call.name != "read_file" or not isinstance(sanitized, str) or sanitized.startswith("Error"):
            return []
        text_path = save_artifact_text(
            self._ctx.session_key,
            self._ctx.turn_id,
            tool_call.id,
            "sanitized_output.txt",
            sanitized,
        )
        return [
            ToolVaultArtifact(
                kind="sanitized_text",
                path=str(text_path),
                mediaType="text/plain",
            )
        ]


def _recorded_output_text(value: Any) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        text = stringify_text_blocks(value) or "(non-text tool output)"
    else:
        text = str(value)

    if len(text) > _MAX_RECORDED_OUTPUT_CHARS:
        return text[:_MAX_RECORDED_OUTPUT_CHARS] + "\n... (truncated)"
    return text


def _contains_placeholder(value: Any) -> bool:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except TypeError:
        text = str(value)
    return bool(PLACEHOLDER_RE.search(text))


def _is_pure_placeholder_text(value: str) -> bool:
    """True iff the string consists solely of vault placeholders + whitespace.

    Such strings have already been tokenized and re-running the PII pipeline
    over them is at best wasted compute, at worst a source of nested or
    misaligned tokens (e.g. a regex matching inside ``<<NAME_12>>``).
    """
    if not value:
        return False
    stripped = PLACEHOLDER_RE.sub("", value).strip()
    return stripped == "" and PLACEHOLDER_RE.search(value) is not None


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_visual_follow_up_message(image_path: str, mime: str, tool_call_id: str) -> dict[str, Any]:
    raw = Path(image_path).read_bytes()
    data_url = "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")
    return {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": (
                    "[Local sanitized file handoff]\n"
                    "The referenced local file has already been read and privacy-sanitized locally. "
                    "Use the attached redacted image as supplemental context for the sanitized tool "
                    "output above. Do not call read_file again for this same file unless the user asks "
                    "for another file or page."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": data_url},
                "_meta": {"path": image_path},
            },
        ],
        "_meta": {"synthetic_tool_handoff": True, "tool_call_id": tool_call_id},
    }


def _local_file_read_rewrite(
    tool_call: ToolCallRequest,
    restored_arguments: Any,
) -> ToolCallRequest | None:
    if tool_call.name != "web_fetch" or not isinstance(restored_arguments, dict):
        return None
    url = restored_arguments.get("url")
    if not isinstance(url, str) or not _looks_like_local_file_path(url):
        return None
    return ToolCallRequest(
        id=tool_call.id,
        name="read_file",
        arguments={"path": url},
        extra_content=tool_call.extra_content,
        provider_specific_fields=tool_call.provider_specific_fields,
        function_provider_specific_fields=tool_call.function_provider_specific_fields,
    )


def _looks_like_local_file_path(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return False
    if parsed.scheme == "file":
        return True
    if text.startswith(("/", "~/", "./", "../")):
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", text))
