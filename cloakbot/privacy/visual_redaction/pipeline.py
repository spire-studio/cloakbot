"""Vault-orchestrating visual privacy pipeline over content blocks.

This is the top of the visual stack: it wires the detector
(:mod:`detector`), OCR matcher (:mod:`ocr_match`), and renderer (:mod:`render`)
to the per-session vault and produces redacted content blocks.

Trust-boundary invariants enforced here:

* **Fail-closed by default** (``CLOAKBOT_VISUAL_FAIL_MODE=omit``): an image is
  replaced by a text placeholder whenever we cannot confidently redact every
  sensitive region — we never forward bytes we cannot prove are safe.
* The detector only *proposes* regions; a box is drawn only after local OCR
  confirms the span, so a hallucinated detector reply cannot leak raw PII.
* Vault placeholders allocated during image redaction are back-substituted into
  the sanitized OCR text, so the textual fallback can never ship a raw value the
  image already redacted.
* The local ``source_path`` is never embedded in LLM-visible content; it stays
  on the :class:`VisualPrivacyRedaction` record for transparency only.

Symbols are looked up through the :mod:`detector` module object (not imported by
name) so a test/eval that rebinds ``detector._inspect_visual`` is honoured by
:func:`_redact_image`.
"""

from __future__ import annotations

import base64
import binascii
import io
import os
import re
from typing import Any

import pytesseract
from loguru import logger
from PIL import Image

from cloakbot.privacy.visual_redaction import detector as _detector
from cloakbot.privacy.visual_redaction.labels import (
    text_entity_type_to_visual_label,
    visual_label_to_tag,
)
from cloakbot.privacy.visual_redaction.models import (
    VisualBlocksResult,
    VisualPrivacyRedaction,
    VisualRedactedRegion,
    VisualVaultEntry,
)
from cloakbot.privacy.visual_redaction.ocr_match import (
    _candidate_needles,
    _filter_ocr_words,
    _image_has_any_ocr_text,
    _matching_text_word_boxes,
    _ocr_data,
    _ocr_regex_items,
    normalize_ocr_text,
)
from cloakbot.privacy.visual_redaction.render import (
    _draw_redactions,
    _format_region_map_text,
)
from cloakbot.utils.helpers import detect_image_mime

_FAIL_MODE_ENV = "CLOAKBOT_VISUAL_FAIL_MODE"
_FAIL_MODE_OMIT = "omit"
_FAIL_MODE_PASS = "pass"


def _visual_fail_mode() -> str:
    """Return the configured fail mode.

    ``omit`` (default, fail-closed) — replace the image with a text placeholder
    whenever we cannot confidently redact every sensitive region.
    ``pass`` (escape hatch) — keep prior behaviour: if zero boxes were drawn,
    still forward the (un-marked) image. Reserved for debugging or for
    environments that explicitly opt out of the conservative default.
    """
    value = os.getenv(_FAIL_MODE_ENV, _FAIL_MODE_OMIT).strip().lower()
    if value not in {_FAIL_MODE_OMIT, _FAIL_MODE_PASS}:
        return _FAIL_MODE_OMIT
    return value


def is_visual_content_blocks(value: Any) -> bool:
    return (
        isinstance(value, list)
        and any(isinstance(item, dict) and item.get("type") == "image_url" for item in value)
    )


def extract_visual_text(blocks: list[Any]) -> str | None:
    parts: list[str] = []
    for block in blocks:
        if not (isinstance(block, dict) and block.get("type") == "image_url"):
            continue
        data_url = ((block.get("image_url") or {}).get("url") if isinstance(block.get("image_url"), dict) else None)
        raw, _mime = _decode_image_data_url(data_url)
        if raw is None:
            continue
        source_path = _source_path(block)
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                image = opened.convert("RGB")
            extracted = normalize_ocr_text(pytesseract.image_to_string(image))
        except Exception as exc:
            logger.warning("visual OCR extraction failed for {}: {}", source_path or "(image)", exc)
            continue
        if not extracted:
            continue
        if source_path:
            parts.append(f"[local OCR extracted from {source_path}]\n{extracted}")
        else:
            parts.append(f"[local OCR extracted from image]\n{extracted}")
    if not parts:
        return None
    return "\n\n".join(parts)


def extract_visual_image(blocks: list[Any]) -> tuple[bytes, str] | None:
    for block in blocks:
        if not (isinstance(block, dict) and block.get("type") == "image_url"):
            continue
        data_url = ((block.get("image_url") or {}).get("url") if isinstance(block.get("image_url"), dict) else None)
        raw, mime = _decode_image_data_url(data_url)
        if raw is not None and mime is not None:
            return raw, mime
    return None


async def redact_visual_content_blocks(
    blocks: list[Any],
    *,
    placeholder_resolver: Any = None,
    text_side_entities: list[tuple[str, str]] | None = None,
) -> tuple[list[Any], bool, list[VisualPrivacyRedaction]]:
    """Run the visual privacy pipeline over a list of content blocks.

    ``placeholder_resolver`` — when supplied — is invoked as
    ``resolver(matched_text, label) -> placeholder | None`` for every
    matched redaction region; the returned placeholder is rendered into
    the black bar so a downstream multimodal model can address each
    redacted area by token. When ``None`` (or when the resolver returns
    ``None``) the box stays solid-black.

    ``text_side_entities`` are ``(text, label)`` tuples forwarded from
    the text-only detector. They give the visual matcher an additional
    set of needles so the image stays in sync when the multimodal
    detector misses entries the text detector caught.
    """
    redacted_blocks: list[Any] = []
    records: list[VisualPrivacyRedaction] = []
    modified = False

    for block in blocks:
        if not (isinstance(block, dict) and block.get("type") == "image_url"):
            redacted_blocks.append(block)
            continue

        source_path = _source_path(block)
        data_url = ((block.get("image_url") or {}).get("url") if isinstance(block.get("image_url"), dict) else None)
        raw, mime = _decode_image_data_url(data_url)
        if raw is None or mime is None:
            redacted_blocks.append(_omitted_block("unsupported image block"))
            records.append(_record(source_path, "omitted", reason="unsupported image block"))
            modified = True
            continue

        try:
            redacted_raw, record = await _redact_image(
                raw,
                mime=mime,
                source_path=source_path,
                placeholder_resolver=placeholder_resolver,
                text_side_entities=text_side_entities,
            )
        except Exception as exc:
            logger.warning("visual privacy redaction failed for {}: {}", source_path or "(image)", exc)
            redacted_blocks.append(_omitted_block(f"visual privacy unavailable: {type(exc).__name__}"))
            records.append(_record(source_path, "omitted", reason=f"visual privacy unavailable: {type(exc).__name__}"))
            modified = True
            continue

        if redacted_raw is None:
            # Fail-closed: detector + OCR could not produce a confident redaction.
            redacted_blocks.append(_omitted_block(record.reason or "fail-closed: no redactable region"))
            records.append(record)
            modified = True
            continue

        new_block = dict(block)
        new_meta = dict(new_block.get("_meta") or {})
        new_meta["visual_privacy"] = record.model_dump(mode="json", by_alias=True)
        # Surface the region map alongside the image so downstream
        # tooling (region-map text block, webui report) can render it
        # without re-parsing the visual_privacy dump.
        if record.regions:
            new_meta["redacted_regions"] = [
                region.model_dump(mode="json") for region in record.regions
            ]
        new_block["_meta"] = new_meta
        new_block["image_url"] = {
            "url": "data:image/png;base64," + base64.b64encode(redacted_raw).decode("ascii")
        }
        redacted_blocks.append(new_block)
        records.append(record)
        modified = True

    return redacted_blocks, modified, records


def _source_path(block: dict[str, Any]) -> str | None:
    meta = block.get("_meta")
    if isinstance(meta, dict) and isinstance(meta.get("path"), str):
        return meta["path"]
    return None


def _decode_image_data_url(data_url: Any) -> tuple[bytes | None, str | None]:
    if not isinstance(data_url, str):
        return None, None
    match = re.fullmatch(r"data:(image/[-+.\w]+);base64,(.*)", data_url, flags=re.DOTALL)
    if not match:
        return None, None
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        return None, None
    mime = detect_image_mime(raw) or match.group(1)
    return raw, mime


def _omitted_block(reason: str) -> dict[str, Any]:
    """Build the LLM-visible placeholder for an omitted image.

    The local ``source_path`` is intentionally *not* embedded here — that
    path can itself be PII (username, customer-named folders, contract
    filenames). It is retained on the :class:`VisualPrivacyRedaction`
    record for transparency reporting only.
    """
    return {
        "type": "text",
        "text": f"[visual content omitted; {reason}]",
    }


def _record(
    source_path: str | None,
    status: str,
    *,
    detected_items: int = 0,
    redaction_boxes: int = 0,
    labels: list[str] | None = None,
    reason: str | None = None,
    regions: list[VisualRedactedRegion] | None = None,
) -> VisualPrivacyRedaction:
    return VisualPrivacyRedaction(
        sourcePath=source_path,
        status=status,
        detectedItems=detected_items,
        redactionBoxes=redaction_boxes,
        labels=labels or [],
        reason=reason,
        regions=regions or [],
    )


async def _redact_image(
    raw: bytes,
    *,
    mime: str,
    source_path: str | None,
    placeholder_resolver: Any = None,
    text_side_entities: list[tuple[str, str]] | None = None,
) -> tuple[bytes | None, VisualPrivacyRedaction]:
    """Run the visual redaction pipeline over one image.

    Returns ``(redacted_png_bytes, record)`` on success. When the pipeline
    cannot produce a confident redaction (fail-closed default) returns
    ``(None, record)`` and the caller is expected to substitute a textual
    placeholder for the image.

    When ``placeholder_resolver`` is supplied, each matched region also
    queries it for a vault placeholder and the placeholder text is
    rendered into the redaction box, so a downstream multimodal model
    can reference the redacted region by token.

    ``text_side_entities`` is an optional list of ``(text, label)`` tuples
    coming from the text-only detector pass. They're matched against OCR
    words **after** the visual detector's items, so even when the local
    multimodal model misses an entity (e.g. a "DMIT, Inc." in the Pay To
    block) the text-side classifier still gets a bbox painted, closing
    the cross-modal recall gap.
    """
    with Image.open(io.BytesIO(raw)) as opened:
        image = opened.convert("RGB")
    analysis = await _detector._inspect_visual(raw, mime=mime, image_size=image.size)
    ocr_data = _ocr_data(image)
    words = _filter_ocr_words(ocr_data)
    has_any_text = _image_has_any_ocr_text(ocr_data)
    items = [item for item in analysis.get("sensitive_items") or [] if isinstance(item, dict)]

    # Phase 1: collect a list of (label, matched_text, bbox) tuples,
    # deduplicated by bbox. This is what we later turn into both the
    # rendered boxes and the structured region map.
    region_candidates: list[tuple[str, str, list[int]]] = []
    seen_boxes: list[list[int]] = []

    def _append_box(label: str, matched_text: str, bbox: list[int]) -> None:
        if bbox in seen_boxes:
            return
        seen_boxes.append(bbox)
        region_candidates.append((label, matched_text, bbox))

    for item in items:
        label = str(item.get("label") or "sensitive")
        item_text = str(item.get("text") or "")
        for needle in _candidate_needles(item):
            for bbox in _matching_text_word_boxes(words, needle):
                _append_box(label, item_text or needle, bbox)

    regex_items = _ocr_regex_items(words)
    for label, value, bbox in regex_items:
        _append_box(label, value, bbox)

    # Text-side fallback: text-only detector caught entities the visual
    # detector may have missed. Match each entity against the same OCR
    # word stream and paint a box if we can locate it. The label is
    # propagated from the privacy registry so downstream consumers see a
    # consistent vendor_name / billing_address / etc.
    text_side_match_count = 0
    if text_side_entities:
        for entity_text, entity_label in text_side_entities:
            if not entity_text:
                continue
            for bbox in _matching_text_word_boxes(words, entity_text):
                before = len(region_candidates)
                _append_box(entity_label, entity_text, bbox)
                if len(region_candidates) > before:
                    text_side_match_count += 1

    detected_items_total = len(items) + len(regex_items) + text_side_match_count
    fail_mode = _visual_fail_mode()
    if not region_candidates and fail_mode == _FAIL_MODE_OMIT and (has_any_text or items):
        # Fail-closed: refuse to forward the image when we either know
        # there *is* text in it (OCR found something printable) or the
        # detector called out items but the local OCR could not pinpoint
        # them.
        reason = (
            "detector reported items but local OCR could not match any"
            if items
            else "image contains text but no redactable region was identified"
        )
        logger.warning(
            "visual privacy fail-closed for {}: {} (items={}, has_text={})",
            source_path or "(image)",
            reason,
            len(items),
            has_any_text,
        )
        return None, _record(
            source_path,
            "omitted",
            detected_items=detected_items_total,
            redaction_boxes=0,
            labels=sorted({label for label, _, _ in region_candidates}),
            reason=f"fail-closed: {reason}",
        )

    # Phase 2: bind each region to a vault placeholder when possible.
    regions: list[VisualRedactedRegion] = []
    for label, matched_text, bbox in region_candidates:
        placeholder: str | None = None
        if placeholder_resolver is not None and matched_text:
            try:
                placeholder = placeholder_resolver(matched_text, label)
            except Exception as exc:  # noqa: BLE001 — never fail the redaction for resolver errors
                logger.warning(
                    "placeholder resolver failed for label={} (image={}): {}",
                    label,
                    source_path or "(image)",
                    exc,
                )
                placeholder = None
        regions.append(
            VisualRedactedRegion(
                bbox=list(bbox),
                label=label,
                matched_text=matched_text or None,
                placeholder=placeholder,
            )
        )

    redacted = _draw_redactions(image, regions)
    out = io.BytesIO()
    redacted.save(out, format="PNG")

    labels_sorted = sorted({region.label for region in regions})
    return out.getvalue(), _record(
        source_path,
        "redacted",
        detected_items=detected_items_total,
        redaction_boxes=len(regions),
        labels=labels_sorted,
        regions=regions,
    )


async def process_visual_blocks(
    blocks: list[Any],
    *,
    session_key: str,
    turn_id: str,
    vault_call_id: str,
    persist_image: bool = True,
    persist_ocr_text: bool = True,
) -> VisualBlocksResult:
    """Run the full visual privacy pipeline over a list of content blocks.

    Shared by the tool-output interceptor and the user-input pre-hook so the
    two entry points cannot diverge in policy. Performs (in order):
      1. ``extract_visual_text`` — local OCR over the *original* image
         bytes (so vault placeholders are allocated before the image
         redaction looks them up).
      2. ``sanitize_tool_output`` — placeholder masking of the OCR text
         so entities land in the session vault.
      3. ``redact_visual_content_blocks`` with a vault-backed
         placeholder resolver — each redaction box is painted with the
         placeholder token (when one can be resolved) so a downstream
         multimodal model can address the region by name.
      4. Insert a per-image region-map text block after each image so
         text-only models still see what was redacted and how to refer
         to it.
      5. Optionally persists the first redacted PNG and the sanitized
         OCR text to the vault under ``vault_call_id``.

    Returns a :class:`VisualBlocksResult`. The caller decides how to weave
    the redacted blocks into messages and how to map :class:`VisualVaultEntry`
    instances into channel-specific records.
    """
    # Lazy imports to avoid import cycles via tool_models / runtime modules.
    from cloakbot.privacy.core.sanitization.sanitize import sanitize_tool_output
    from cloakbot.privacy.core.state.vault import (
        get_map,
        save_artifact_bytes,
        save_artifact_text,
        save_map,
    )

    # Phase 1: OCR + text-side sanitization first so the vault has the
    # placeholders ready when the resolver below queries it.
    extracted_text = extract_visual_text(blocks)
    sanitized_text, text_modified, entities = await sanitize_tool_output(
        extracted_text or "",
        session_key,
        turn_id=turn_id,
    )

    smap = get_map(session_key)
    smap_before = _count_placeholders(smap)

    def _resolver(matched_text: str, label: str) -> str | None:
        if not matched_text:
            return None
        tag = visual_label_to_tag(label)
        placeholder, _ = smap.get_or_create_placeholder(
            matched_text,
            tag,
            turn_id=turn_id,
        )
        return placeholder

    # Cross-modal recall bridge: feed every text-side entity into the
    # visual matcher as an additional needle. This is what catches
    # cases where the multimodal model overlooked a span ("DMIT, Inc."
    # in the Pay To block) but the text-side classifier flagged it
    # from the OCR stream — without this, the image would still ship
    # the value in plain text even though the OCR fallback is masked.
    text_side_needles: list[tuple[str, str]] = []
    for entity in entities:
        entity_text = getattr(entity, "text", None)
        entity_type = getattr(entity, "entity_type", None)
        if not entity_text or not entity_type:
            continue
        text_side_needles.append(
            (entity_text, text_entity_type_to_visual_label(entity_type))
        )

    redacted_blocks, visual_modified, visual_redactions = await redact_visual_content_blocks(
        blocks,
        placeholder_resolver=_resolver,
        text_side_entities=text_side_needles or None,
    )

    # Persist any placeholder allocations the resolver produced and
    # *back-substitute* them into the OCR text. The visual detector
    # often catches PII the text-side detector misses (multi-column
    # invoice layouts, decorative fonts, low-confidence OCR words)
    # — without this step the image is redacted but the OCR text
    # fallback still ships the raw value to the remote LLM.
    if _count_placeholders(smap) != smap_before:
        save_map(session_key, smap)
        visual_modified = True
        if sanitized_text:
            sanitized_text, replaced = smap.replace_known_originals(sanitized_text)
            if replaced:
                text_modified = True

    redacted_blocks = _interleave_region_maps(redacted_blocks)

    vault_entries: list[VisualVaultEntry] = []
    if persist_image:
        # Persist the *original* image alongside the redacted version so the
        # WebUI can rebuild the local-vs-remote diff after a page reload —
        # the frontend only holds the original in-memory and loses it on
        # refresh. Both artifacts live under the per-session vault on the
        # user's own machine, so this does not widen the network boundary
        # (the contract is "nothing leaves localhost", not "nothing touches
        # disk"). Order matters: the original is appended first so the
        # builder can pair it positionally with the redaction record.
        original_image = extract_visual_image(blocks)
        if original_image is not None:
            raw, mime = original_image
            suffix = _mime_suffix(mime)
            original_path = save_artifact_bytes(
                session_key,
                turn_id,
                vault_call_id,
                f"original_image.{suffix}",
                raw,
            )
            vault_entries.append(
                VisualVaultEntry(kind="original_image", path=str(original_path), media_type=mime)
            )

        visual_image = extract_visual_image(redacted_blocks)
        if visual_image is not None:
            raw, mime = visual_image
            suffix = _mime_suffix(mime)
            image_path = save_artifact_bytes(
                session_key,
                turn_id,
                vault_call_id,
                f"redacted_image.{suffix}",
                raw,
            )
            vault_entries.append(
                VisualVaultEntry(kind="redacted_image", path=str(image_path), media_type=mime)
            )
    if persist_ocr_text and sanitized_text:
        text_path = save_artifact_text(
            session_key,
            turn_id,
            vault_call_id,
            "ocr_sanitized.txt",
            sanitized_text,
        )
        vault_entries.append(
            VisualVaultEntry(kind="ocr_sanitized_text", path=str(text_path), media_type="text/plain")
        )

    image_count = sum(
        1 for b in blocks if isinstance(b, dict) and b.get("type") == "image_url"
    )
    omitted_count = sum(
        1 for b in redacted_blocks if isinstance(b, dict) and b.get("type") == "text"
    ) - sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "text")

    return VisualBlocksResult(
        redacted_blocks=redacted_blocks,
        sanitized_text=sanitized_text,
        modified=visual_modified or text_modified,
        entities=list(entities),
        visual_redactions=visual_redactions,
        vault_entries=vault_entries,
        omitted_count=max(0, omitted_count),
        image_count=image_count,
    )


def _mime_suffix(mime: str) -> str:
    if mime == "image/png":
        return "png"
    if mime == "image/jpeg":
        return "jpg"
    if mime == "image/webp":
        return "webp"
    return "bin"


def _count_placeholders(smap: Any) -> int:
    """Best-effort placeholder-count probe so we can detect new allocations.

    Falls back to ``0`` if the vault internals change shape — the worst
    case is one extra ``save_map`` call, which is cheap.
    """
    try:
        return len(smap.placeholder_to_entity)
    except AttributeError:
        return 0


def _interleave_region_maps(blocks: list[Any]) -> list[Any]:
    """Insert a region-map text block after each image with redactions.

    The text block is what makes the placeholder-in-box rendering useful
    to text-mostly LLMs: it lists each ``placeholder → label + bbox``
    pair, never the original PII value, so the model can answer with
    ``"The customer in <<PERSON_1>>…"`` and the local restorer fills it
    in for the user-facing reply.
    """
    out: list[Any] = []
    for block in blocks:
        out.append(block)
        if not isinstance(block, dict) or block.get("type") != "image_url":
            continue
        regions = (block.get("_meta") or {}).get("redacted_regions") or []
        text = _format_region_map_text(regions)
        if text:
            out.append({"type": "text", "text": text})
    return out


__all__ = [
    "extract_visual_image",
    "extract_visual_text",
    "is_visual_content_blocks",
    "process_visual_blocks",
    "redact_visual_content_blocks",
]
