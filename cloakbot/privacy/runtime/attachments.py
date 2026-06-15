"""Decoding of user-attached media references into model-ready blocks.

Pure, ctx-free helpers that turn raw ``media=[...]`` references (inline data URLs
or filesystem paths) into image ``image_url`` blocks and decoded text-document
tuples. The privacy orchestration around these — running the visual pipeline,
persisting vault artifacts, chunked document detection — stays in
:mod:`cloakbot.privacy.runtime.pipeline`; this module only parses bytes.

Logging never prints a raw reference: data URLs carry the user's raw bytes in
base64 and even filesystem paths can include sensitive folder names, so failures
log a short :func:`media_fingerprint` instead.
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import re
from pathlib import Path
from typing import Any

from loguru import logger

from cloakbot.utils.helpers import detect_image_mime

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


def decode_data_url(reference: str) -> tuple[bytes, str | None] | None:
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


def document_suffix(mime: str) -> str:
    """File extension to use when persisting an uploaded document.

    Kept conservative — only the MIMEs that pass
    :data:`_SUPPORTED_DOCUMENT_MIMES` should reach here, and we want a
    short stable suffix per family so a glob over the vault can find
    "all user-uploaded contracts" without parsing every file.
    """
    return {"text/plain": "txt", "text/markdown": "md"}.get(mime, "txt")


def media_fingerprint(reference: str) -> str:
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


def build_image_blocks_from_media(media: list[str]) -> list[dict[str, Any]]:
    """Read media references into ``image_url`` blocks for visual processing.

    Accepts two reference shapes:

    - ``data:image/<mime>;base64,<payload>`` — inline data URLs sent by
      the WebUI/clipboard path. Parsed in-memory; the source ``path``
      metadata is suppressed because the original filename/contents
      have no on-disk anchor.
    - Filesystem paths (legacy channel uploads via Feishu/Slack/QQ).
      Read with the same constraints as
      ``agent.context.ContextBuilder._build_user_content``.

    Warning logs **never** print the raw reference (see module docstring).
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
            raw_mime: tuple[bytes, str | None] | None = decode_data_url(reference)
            if raw_mime is None:
                logger.warning(
                    "cannot decode user-attached media: {} ({} chars)",
                    media_fingerprint(reference),
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
                media_fingerprint(reference),
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


def extract_documents_from_media(media: list[str]) -> list[tuple[str, str, str | None]]:
    """Decode ``data:text/...`` entries to ``(text, mime, name)`` tuples.

    Image data URLs and on-disk paths are skipped — the visual pipeline picks
    those up separately in :func:`build_image_blocks_from_media`. Anything that
    decodes but exceeds ``_MAX_DOCUMENT_CHARS`` is dropped with a sanitized log
    line; we don't want a 1MB paste to dominate latency.

    Document names are not part of the data URL spec — channels that want to
    surface a filename should encode it into the attachment metadata
    (``WebUIAttachment.name``) which is threaded separately. This helper returns
    ``None`` for the name slot and lets the caller fill it in if available.
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
                media_fingerprint(reference),
                len(reference),
            )
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "user-uploaded document is not valid UTF-8: {}",
                media_fingerprint(reference),
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


__all__ = [
    "build_image_blocks_from_media",
    "decode_data_url",
    "document_suffix",
    "extract_documents_from_media",
    "media_fingerprint",
]
