"""Outbound visual/multimodal egress gate for image generation (Cap E).

The ``generate_image`` tool sends a *prompt* and zero or more *reference images*
to a remote image-generation endpoint (OpenRouter / AIHubMix / Gemini / …). Cap C
already classifies ``generate_image`` ``EXTERNAL`` in the
:class:`~cloakbot.privacy.egress_policy.EgressPolicy`, so the tool call itself is
approval-gated. But classification alone does not scrub the bytes that leave: a
user-supplied reference photo of an invoice, ID card, or screenshot would still
ship verbatim to the remote model, and the natural-language prompt may carry raw
PII the user typed ("make a poster for John Smith at 12 Acacia Ave").

This module is the **outbound bytes** half of that protection. It is a thin,
privacy-owned wrapper around an
:class:`~cloakbot.providers.image_generation.ImageGenerationProvider` that
brackets ``generate``:

* **Reference images** are routed through
  :func:`~cloakbot.privacy.visual_redaction.process_visual_blocks` — the same
  detection + local OCR redaction pipeline (fail-closed) the tool-output
  interceptor and the user-input pre-hook share. Each reference is OCR'd,
  sensitive regions are painted over locally, and only the *redacted* PNG is
  forwarded. When the pipeline cannot confidently redact an image
  (``CLOAKBOT_VISUAL_FAIL_MODE=omit`` default) the image is **omitted entirely**
  rather than shipped raw — fail-closed.
* **The prompt** is routed through
  :func:`~cloakbot.privacy.core.sanitization.sanitize.sanitize_input_with_detection`
  so any raw entity the user typed is replaced by its vault placeholder before
  the prompt leaves the host. ``fail_open=False`` here: if the local detector is
  unavailable we refuse to forward an unsanitized prompt to the remote model
  (consistent with the fail-closed posture of the image path).

It mirrors the Cap C ``provider_egress_gate`` pattern (an additive subclass-style
wrapper installed at provider-factory time) and the Cap D
``compaction_provider`` pattern (transparent attribute delegation to the inner
provider). It never edits ``providers/image_generation.py``.

The redacted reference PNGs are written to the per-session vault on the user's
own machine (same boundary as the visual tool-output path: "nothing leaves
localhost", not "nothing touches disk").
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from cloakbot.privacy.core.sanitization.sanitize import sanitize_input_with_detection
from cloakbot.privacy.core.state.vault import route_fixed_key_through_active_run
from cloakbot.privacy.visual_redaction import (
    VisualBlocksResult,
    process_visual_blocks,
)
from cloakbot.providers.image_generation import ImageGenerationError
from cloakbot.utils.helpers import detect_image_mime

# Stable session key under which image-gen egress allocates / reuses placeholders.
# The tool is not turn-scoped at the provider seam, so — like the Cap D
# compaction key — a dedicated stable key keeps the contract explicit and routes
# through the Cap B scope table (the user's shared vault).
_VISUAL_EGRESS_SESSION_KEY = "image_gen"
_VISUAL_EGRESS_TURN_PREFIX = "imggen"


def _read_image_data_url(path: str | Path) -> tuple[str, bytes, str] | None:
    """Return ``(data_url, raw_bytes, mime)`` for a local image, or ``None``.

    ``None`` means the path is unreadable or not a supported image — callers
    fail-closed by omitting it from the outbound reference set.
    """
    try:
        raw = Path(path).expanduser().read_bytes()
    except OSError as exc:
        logger.bind(privacy="egress").warning(
            "visual egress: reference image unreadable ({}): {}", path, exc
        )
        return None
    mime = detect_image_mime(raw)
    if mime is None:
        logger.bind(privacy="egress").warning(
            "visual egress: reference image unsupported mime ({})", path
        )
        return None
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}", raw, mime


def _reference_blocks(paths: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Build ``image_url`` blocks for redaction; return ``(blocks, omitted)``.

    ``omitted`` collects paths we could not even decode (fail-closed: they are
    dropped from the outbound set, never forwarded raw).
    """
    blocks: list[dict[str, Any]] = []
    omitted: list[str] = []
    for path in paths:
        decoded = _read_image_data_url(path)
        if decoded is None:
            omitted.append(path)
            continue
        data_url, _raw, _mime = decoded
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": data_url},
                "_meta": {"path": str(path)},
            }
        )
    return blocks, omitted


def _block_redaction_region_count(block: dict[str, Any]) -> int:
    """How many confident redaction regions the pipeline drew on *block*.

    Reads the per-block ``_meta["visual_privacy"]`` record the redaction
    pipeline stamps. ``redactionBoxes`` (camelCase, the pydantic alias) is the
    authoritative count; ``redacted_regions`` is a fallback when only the region
    list is present. Returns 0 when the meta is missing — which the M2 gate
    treats as "no confident redaction", fail-closed.
    """
    meta = block.get("_meta")
    if not isinstance(meta, dict):
        return 0
    record = meta.get("visual_privacy")
    if isinstance(record, dict):
        boxes = record.get("redactionBoxes", record.get("redaction_boxes"))
        if isinstance(boxes, int):
            return boxes
        regions = record.get("regions")
        if isinstance(regions, list):
            return len(regions)
    regions = meta.get("redacted_regions")
    if isinstance(regions, list):
        return len(regions)
    return 0


def _redacted_paths_from_result(
    result: VisualBlocksResult,
    *,
    session_key: str,
    turn_id: str,
    vault_call_id: str,
) -> list[str]:
    """Persist each *redacted* image block to the vault and return its path.

    Blocks that the pipeline turned into a ``text`` placeholder (fail-closed
    omission) contribute *no* path — the corresponding reference image is
    dropped from the outbound set, never shipped raw.

    [Cap E / M2] Fail-closed-by-default for the image-gen EGRESS path: a
    reference image that produced **zero confident redaction regions** (e.g. a
    photo with no OCR text and no detector items, where the shared redaction
    pipeline would otherwise forward the ORIGINAL bytes) is **omitted** here.
    A user-supplied reference is opaque bytes we cannot prove are safe, so unlike
    the tool-output OCR path we never forward an un-redacted reference image to
    the remote image-gen endpoint.
    """
    from cloakbot.privacy.core.state.vault import save_artifact_bytes

    out: list[str] = []
    index = 0
    for block in result.redacted_blocks:
        if not (isinstance(block, dict) and block.get("type") == "image_url"):
            # An omitted/region-map/text block: not a forwardable image.
            continue
        url = (block.get("image_url") or {}).get("url") if isinstance(block.get("image_url"), dict) else None
        if not isinstance(url, str) or not url.startswith("data:image/"):
            continue
        if _block_redaction_region_count(block) <= 0:
            # M2: no confident redaction region -> the bytes may be the original
            # reference. Omit it from the outbound set rather than ship it raw.
            logger.bind(privacy="egress").warning(
                "visual egress: omitting reference image with zero confident "
                "redaction regions (fail-closed image-gen egress)"
            )
            continue
        try:
            _header, b64 = url.split(",", 1)
            raw = base64.b64decode(b64, validate=True)
        except Exception:  # noqa: BLE001 - any decode failure -> skip (fail-closed)
            continue
        path = save_artifact_bytes(
            session_key,
            turn_id,
            vault_call_id,
            f"redacted_reference_{index}.png",
            raw,
        )
        out.append(str(path))
        index += 1
    return out


class VisualEgressGatedImageProvider:
    """Wrap an image-gen provider so reference images + prompt are scrubbed.

    Transparent delegation (Cap D pattern): every attribute except ``generate``
    is forwarded to the wrapped provider. ``generate`` is bracketed with the
    visual redaction pipeline (reference images) and input sanitization (prompt)
    before the call reaches the remote endpoint.
    """

    def __init__(
        self,
        inner: Any,
        *,
        session_key: str = _VISUAL_EGRESS_SESSION_KEY,
    ) -> None:
        self._inner = inner
        self._session_key = session_key

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def inner(self) -> Any:
        return self._inner

    async def _sanitize_prompt(self, prompt: str, *, turn_id: str) -> str:
        """Placeholder the prompt before it reaches the remote endpoint.

        ``fail_open=False`` (fail-CLOSED): the image-gen prompt goes to a REMOTE
        endpoint and can carry raw PII the user typed ("make a poster for John
        Smith at 12 Acacia Ave"). If the local detector is unavailable we cannot
        confirm the prompt is scrubbed, so we refuse to forward an unsanitized
        prompt — the underlying call raises and :meth:`generate` blocks/omits the
        image-gen request rather than shipping a raw prompt. This matches the
        module's stated (stronger) fail-closed contract and the reference-image
        omit gate.
        """
        if not prompt:
            return prompt
        sanitized, _modified, _entities, _detection = await sanitize_input_with_detection(
            prompt,
            self._session_key,
            fail_open=False,
            turn_id=turn_id,
        )
        return sanitized

    async def _redact_reference_images(
        self,
        reference_images: list[str],
        *,
        turn_id: str,
    ) -> list[str]:
        """Return redacted local paths for *reference_images* (fail-closed).

        Each image is OCR-redacted locally; images that cannot be confidently
        redacted are dropped (the omitted placeholder block carries no path), so
        a sensitive reference never leaves the host unredacted.
        """
        blocks, omitted = _reference_blocks(reference_images)
        if omitted:
            logger.bind(privacy="egress").warning(
                "visual egress: {} reference image(s) omitted (undecodable)", len(omitted)
            )
        if not blocks:
            return []

        result = await process_visual_blocks(
            blocks,
            session_key=self._session_key,
            turn_id=turn_id,
            vault_call_id=turn_id,
            persist_image=False,
            persist_ocr_text=False,
        )
        return _redacted_paths_from_result(
            result,
            session_key=self._session_key,
            turn_id=turn_id,
            vault_call_id=turn_id,
        )

    async def generate(
        self,
        *,
        prompt: str,
        model: str,
        reference_images: list[str] | None = None,
        aspect_ratio: str | None = None,
        image_size: str | None = None,
    ) -> Any:
        turn_id = f"{_VISUAL_EGRESS_TURN_PREFIX}_{uuid.uuid4().hex[:12]}"

        # [Cap B / M3] The image-gen seam uses a fixed shared key
        # (``image_gen``). If an ephemeral run (dream / cron) generates an image,
        # route the placeholder mint into that run's memory-only ephemeral scope
        # so it never lands at maps/image_gen.json on disk. No-op on normal turns.
        with route_fixed_key_through_active_run(self._session_key):
            # [Cap E / H3] Fail-CLOSED on the prompt: if the local detector is
            # unavailable we cannot confirm the prompt is scrubbed, so block the
            # image-gen call instead of shipping a raw prompt to the remote model.
            try:
                safe_prompt = await self._sanitize_prompt(prompt, turn_id=turn_id)
            except Exception as exc:  # noqa: BLE001 - detector outage -> block egress
                logger.bind(privacy="egress").warning(
                    "visual egress: blocking image-gen (prompt could not be "
                    "sanitized fail-closed): {}",
                    exc,
                )
                raise ImageGenerationError(
                    "image generation blocked: the local privacy detector is "
                    "unavailable, so the prompt could not be sanitized before "
                    "leaving the host"
                ) from exc

            refs = list(reference_images or [])
            safe_refs: list[str] = []
            if refs:
                safe_refs = await self._redact_reference_images(refs, turn_id=turn_id)

        return await self._inner.generate(
            prompt=safe_prompt,
            model=model,
            reference_images=safe_refs or None,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )


def wrap_image_provider_with_visual_egress_gate(
    provider: Any,
    *,
    session_key: str = _VISUAL_EGRESS_SESSION_KEY,
) -> Any:
    """Wrap an image-gen provider with the Cap E visual egress gate (idempotent).

    Returns *provider* unchanged when it is ``None`` or already gated, so the
    factory-time install is a no-op on re-entry.
    """
    if provider is None or isinstance(provider, VisualEgressGatedImageProvider):
        return provider
    return VisualEgressGatedImageProvider(provider, session_key=session_key)


__all__ = [
    "VisualEgressGatedImageProvider",
    "wrap_image_provider_with_visual_egress_gate",
]
