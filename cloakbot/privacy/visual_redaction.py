from __future__ import annotations

import base64
import binascii
import io
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import pytesseract
from json_repair import repair_json
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field

from cloakbot.providers.detector import get_detector_client, get_detector_model
from cloakbot.utils.helpers import detect_image_mime

_FAIL_MODE_ENV = "CLOAKBOT_VISUAL_FAIL_MODE"
_FAIL_MODE_OMIT = "omit"
_FAIL_MODE_PASS = "pass"

# Visual detector labels → privacy-registry tags. Used by the
# placeholder resolver so a box detected as ``customer_name`` ends up
# sharing the same vault placeholder family as a free-text ``person``
# detection elsewhere in the same session.
_VISUAL_LABEL_TO_TAG: dict[str, str] = {
    "vendor_name": "ORG",
    "customer_name": "PERSON",
    "billing_address": "ADDRESS",
    "shipping_address": "ADDRESS",
    "email": "EMAIL",
    "phone": "PHONE",
    "tax_id": "ID",
    "invoice_number": "ID",
    "account_number": "ID",
    "bank_info": "ID",
    "transaction_id": "ID",
    "payment_gateway": "ORG",
    "service_code": "ID",
    "date": "DATE",
    "amount": "FINANCE",
    "line_item": "FINANCE",
    "other": "ENTITY",
}

# Inverse mapping: text-detector entity slug → preferred visual label.
# Used when forwarding text-side entities into the visual matcher so
# the bbox a text-only catch ends up with carries a label the rest of
# the visual pipeline can route on (region map, vault tag).
_TEXT_ENTITY_TYPE_TO_VISUAL_LABEL: dict[str, str] = {
    "person": "customer_name",
    "org": "vendor_name",
    "address": "billing_address",
    "email": "email",
    "phone": "phone",
    "identifier": "transaction_id",
    "url": "service_code",
    "local_path": "service_code",
    "credential": "other",
    "medical": "other",
    "ip_address": "other",
    "temporal": "date",
    "financial": "amount",
    "percentage": "amount",
    "amount": "amount",
    "measurement": "amount",
    "value": "amount",
}


def text_entity_type_to_visual_label(entity_type: str) -> str:
    return _TEXT_ENTITY_TYPE_TO_VISUAL_LABEL.get(entity_type, "other")


def visual_label_to_tag(label: str) -> str:
    """Map a visual detector label to a privacy-registry tag, default ``ENTITY``."""
    return _VISUAL_LABEL_TO_TAG.get(label, "ENTITY")


# Callback that turns ``(matched_text, label)`` into a vault placeholder.
# Implementations live close to the session vault and decide whether
# to look up an existing token or allocate a fresh one. ``None`` from
# the resolver means "do not bind a placeholder — fall back to a plain
# black redaction box".
PlaceholderResolver = "Callable[[str, str], str | None]"


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

_SYSTEM_PROMPT = """You are a local privacy inspector for invoices and financial documents.

You will receive one document page image. Identify privacy-sensitive visible text
that must be redacted before the page is sent to an untrusted remote LLM.

Return ONLY valid JSON with this schema:
{
  "document_type": "invoice|receipt|statement|other",
  "sensitive_items": [
    {
      "label": "vendor_name|customer_name|billing_address|shipping_address|email|phone|tax_id|invoice_number|account_number|bank_info|transaction_id|payment_gateway|service_code|date|amount|line_item|other",
      "text": "exact visible text if readable",
      "reason": "why this is sensitive",
      "confidence": 0.0
    }
  ]
}

Prefer high recall for invoices: names, addresses, emails, account IDs, invoice
numbers, transaction IDs, dates, money amounts, and line item details can all be
sensitive in private documents.

Additional recall hints — DO extract these (they are private when attached to a
specific customer's document, even though the brand names themselves are public):

  * payment_gateway: Alipay, WeChat Pay, UnionPay, Stripe, PayPal, Square,
    Adyen, Braintree, ApplePay, GooglePay, and similar processor names that
    appear next to a transaction. Their presence reveals the customer's payment
    relationship.
  * service_code: internal service / product / instance identifiers that look
    like "LAX.AN4.Pro.TINY", "DMIT-US-1", "us-west-2-i-0a1b2c3d", or any
    dot/hyphen-separated alphanumeric code in a line item or description.
  * transaction_id: long compound IDs (>= 16 chars), including those joined by
    "|", "-", "_", or "." separators — extract the *entire* span as one item.
  * date: every visible date on the page (issue date, transaction date,
    billing period start/end, due date). Do not skip "templated"-looking dates.
"""


class VisualRedactedRegion(BaseModel):
    """One bbox-level redaction on an image, optionally bound to a vault placeholder.

    The placeholder is what makes the redaction transparent to a remote
    multimodal model: the box renders the placeholder token (e.g.
    ``<<PERSON_1>>``) instead of an opaque black bar, and the same token
    appears in the textual region-map alongside the image, so the model
    can refer to "the person in <<PERSON_1>>" and the local restorer
    swaps it back to the real value in the user-facing reply.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    placeholder: str | None = None
    bbox: list[int]
    label: str
    # ``matched_text`` is retained for transparency reports only. It is
    # the OCR-extracted token that anchored this region — never the raw
    # PII value as it appeared in the image. Callers must not surface
    # it to remote models.
    matched_text: str | None = None


class VisualPrivacyRedaction(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_path: str | None = Field(default=None, alias="sourcePath")
    status: str
    detected_items: int = Field(alias="detectedItems")
    redaction_boxes: int = Field(alias="redactionBoxes")
    labels: list[str] = Field(default_factory=list)
    reason: str | None = None
    regions: list[VisualRedactedRegion] = Field(default_factory=list)


@dataclass(frozen=True)
class _TextWord:
    text: str
    token: str
    bbox: list[int]


@dataclass(frozen=True)
class VisualVaultEntry:
    """Vault-bound artifact produced by visual processing.

    Kept as a plain dataclass to avoid a circular import with
    ``cloakbot.privacy.tool_models`` (which itself imports
    :class:`VisualPrivacyRedaction` from this module). Callers convert these
    into ``ToolVaultArtifact`` instances at the boundary.
    """

    kind: str
    path: str
    media_type: str | None = None


@dataclass
class VisualBlocksResult:
    """Outcome of running the visual privacy pipeline over content blocks."""

    redacted_blocks: list[dict[str, Any]] = field(default_factory=list)
    sanitized_text: str = ""
    modified: bool = False
    entities: list[Any] = field(default_factory=list)
    visual_redactions: list["VisualPrivacyRedaction"] = field(default_factory=list)
    vault_entries: list[VisualVaultEntry] = field(default_factory=list)
    omitted_count: int = 0
    image_count: int = 0


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
            extracted = _normalize_ocr_text(pytesseract.image_to_string(image))
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
    analysis = await _inspect_visual(raw, mime=mime, image_size=image.size)
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


async def _inspect_visual(raw: bytes, *, mime: str, image_size: tuple[int, int]) -> dict[str, Any]:
    client = get_detector_client()
    width, height = image_size
    response = await client.chat.completions.create(
        model=get_detector_model(),
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Inspect this document page for sensitive visible information. "
                            f"Image size: width={width}px, height={height}px."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                        },
                    },
                ],
            },
        ],
        temperature=0,
        max_tokens=2048,
        stream=False,
        response_format={"type": "json_object"},
    )
    raw_text = response.choices[0].message.content or "{}"
    return _parse_model_json(raw_text)


def _parse_model_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = json.loads(repair_json(cleaned))
    return parsed if isinstance(parsed, dict) else {}


def _normalize_ocr_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in str(text or "").splitlines()]
    cleaned = [line for line in lines if line]
    return "\n".join(cleaned).strip()


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("|", " ").split())


def _match_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_text(text).lower())


def _tokens_for_match(text: str) -> list[str]:
    return [token for token in (_match_key(part) for part in _normalize_text(text).split()) if token]


def _candidate_needles(item: dict[str, Any]) -> list[str]:
    text = _normalize_text(str(item.get("text") or ""))
    if not text:
        return []

    candidates = [text]
    candidates.extend(part.strip() for part in re.split(r"[,;\n]", text) if part.strip())

    label = str(item.get("label") or "")
    if label == "invoice_number":
        match = re.search(r"(?:Invoice\s*#\s*)?([A-Z0-9]+-[A-Z0-9-]+)", text, re.IGNORECASE)
        if match:
            candidates.extend([match.group(0), match.group(1)])
    elif label == "transaction_id":
        candidates.extend(re.findall(r"[A-Z0-9|_-]{12,}", text))
    elif label in {"date", "amount"}:
        candidates.extend(re.findall(r"\$?[0-9][\w\s./,-]*(?:USD|usd|%)?", text))

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        candidate = _normalize_text(candidate)
        if len(candidate) < 4 or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _ocr_data(image: Image.Image) -> dict[str, Any]:
    """Single underlying ``image_to_data`` call shared by all OCR paths."""
    return pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)


def _image_has_any_ocr_text(data: dict[str, Any]) -> bool:
    """Cheap "is there any printable text on this page" probe.

    Ignores Tesseract confidence so we still detect text-bearing images even
    when language packs are missing (which is exactly when fail-closed must
    trigger — Latin-only OCR misses CJK / Arabic / Cyrillic content).
    """
    for value in data.get("text", []):
        if str(value or "").strip():
            return True
    return False


def _ocr_text_words(image: Image.Image) -> list[_TextWord]:
    return _filter_ocr_words(_ocr_data(image))


def _filter_ocr_words(data: dict[str, Any]) -> list[_TextWord]:
    words: list[tuple[tuple[int, int, int, int], _TextWord]] = []
    for i, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text or "").strip()
        if not text:
            continue
        # Tesseract reports ``conf=-1`` for both layout-marker rows
        # (already filtered above by the empty-text guard) *and* for a
        # subset of genuine word entries it could not confidence-rate.
        # We accept every entry that survives the empty-text check —
        # the matcher downstream only paints a bbox when the OCR
        # token literally satisfies a needle key, so spurious
        # low-confidence words cannot trigger over-redaction. The A2
        # visual leak eval surfaced this as a recurring miss on
        # customer-side emails (single-token fuzzy path could not see
        # the OCR word because the filter had dropped it).
        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])
        token = _match_key(text)
        if width <= 0 or height <= 0 or not token:
            continue
        order_key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
            int(data["word_num"][i]),
        )
        words.append((order_key, _TextWord(text=text, token=token, bbox=[left, top, left + width, top + height])))
    return [word for _order, word in sorted(words, key=lambda item: item[0])]


def _union_boxes(boxes: list[list[int]]) -> list[int]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _matching_text_word_boxes(words: list[_TextWord], needle: str) -> list[list[int]]:
    needle_tokens = _tokens_for_match(needle)
    if not needle_tokens:
        return []
    if len(needle_tokens) == 1:
        needle_token = needle_tokens[0]
        boxes: list[list[int]] = []
        for word in words:
            exact = word.token == needle_token
            long_fuzzy = (
                len(needle_token) >= 8
                and len(word.token) >= 8
                and (needle_token in word.token or word.token in needle_token)
            )
            if exact or long_fuzzy:
                boxes.append(word.bbox)
        return boxes

    boxes = []
    tokens = [word.token for word in words]
    needle_len = len(needle_tokens)

    # Pass 1 — strict consecutive match.
    # When OCR is clean, every needle token has an exact OCR neighbour
    # in the same order, so a strict window comparison gives a precise
    # bbox without any over-redaction risk.
    for start in range(0, len(tokens) - needle_len + 1):
        if tokens[start : start + needle_len] == needle_tokens:
            boxes.append(_union_boxes([word.bbox for word in words[start : start + needle_len]]))
    if boxes:
        return boxes

    # Pass 2 — gap-tolerant fallback.
    # Tesseract regularly misreads one or two internal tokens in long
    # spans ("Suite" → "Sulte", "AZ" → "A2"), which kills the strict
    # match for the whole window and leaves the *entire* address
    # unredacted. We accept any equal-length window whose tokens
    # intersect the needle set at ≥ 70%. Over-redaction is bounded
    # because the window size is pinned to ``needle_len`` and the
    # threshold rejects accidental clusters of common words. Surfaced
    # as a recurring leak on customer addresses by the A2 visual eval.
    needle_set = {token for token in needle_tokens if token}
    if not needle_set or needle_len < 3:
        return boxes
    threshold = max(2, (needle_len * 7 + 9) // 10)  # ceil(needle_len * 0.7)
    for start in range(0, len(tokens) - needle_len + 1):
        window = tokens[start : start + needle_len]
        if sum(1 for token in window if token in needle_set) >= threshold:
            boxes.append(_union_boxes([word.bbox for word in words[start : start + needle_len]]))
    return boxes


def _ocr_regex_items(words: list[_TextWord]) -> list[tuple[str, str, list[int]]]:
    items: list[tuple[str, str, list[int]]] = []
    for i, word in enumerate(words):
        text = word.text
        if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
            items.append(("email", text, word.bbox))
        if re.fullmatch(r"#?[A-Z0-9]+-[A-Z0-9-]+", text) and len(word.token) > 10:
            items.append(("invoice_number", text, word.bbox))
        if re.fullmatch(r"\d{10,}[A-Z0-9|_-]{8,}", text):
            items.append(("transaction_id", text, word.bbox))
        if re.fullmatch(r"\(?\d{2}/\d{2}/\d{4}\)?", text):
            items.append(("date", text.strip("()"), word.bbox))
        if re.fullmatch(r"\$[0-9][0-9,.]*", text):
            boxes = [word.bbox]
            value = text
            if i + 1 < len(words) and words[i + 1].token == "usd":
                boxes.append(words[i + 1].bbox)
                value = f"{value} {words[i + 1].text}"
            items.append(("amount", value, _union_boxes(boxes)))
    return items


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


def _format_region_map_text(regions: list[dict[str, Any]]) -> str | None:
    """Render the region-map text block. Returns ``None`` for no regions.

    Regions are *deduplicated by placeholder/label token* so the same
    address spanning two OCR lines (or the same company name OCR'd as
    two words) is announced exactly once. Without this collapse the
    downstream LLM treats repeated tokens as separate entities and
    repeats their values in its reply.
    """
    if not regions:
        return None
    lines = [
        "[Image redaction map — placeholders below appear as overlay text in the image above. "
        "Reference them verbatim in your reply; the local restorer will substitute originals.]"
    ]

    grouped: dict[str, dict[str, Any]] = {}
    token_order: list[str] = []
    for region in regions:
        placeholder = region.get("placeholder")
        label = region.get("label") or "redacted"
        token = placeholder if placeholder else f"<<{label.upper()}>>"
        bbox = region.get("bbox") or []
        bucket = grouped.setdefault(
            token,
            {
                "placeholder": placeholder,
                "label": label,
                "bboxes": [],
            },
        )
        if not grouped or token not in token_order:
            token_order.append(token)
        if len(bbox) == 4:
            bucket["bboxes"].append(list(bbox))

    # Preserve first-seen order so the textual map mirrors the visual
    # left-to-right top-to-bottom reading pattern.
    seen: set[str] = set()
    ordered_tokens: list[str] = []
    for region in regions:
        placeholder = region.get("placeholder")
        label = region.get("label") or "redacted"
        token = placeholder if placeholder else f"<<{label.upper()}>>"
        if token in seen:
            continue
        seen.add(token)
        ordered_tokens.append(token)

    for token in ordered_tokens:
        bucket = grouped[token]
        placeholder = bucket["placeholder"]
        label = bucket["label"]
        bboxes = bucket["bboxes"]
        if bboxes:
            x1 = min(b[0] for b in bboxes)
            y1 = min(b[1] for b in bboxes)
            x2 = max(b[2] for b in bboxes)
            y2 = max(b[3] for b in bboxes)
            bbox_str = f"({x1},{y1})–({x2},{y2})"
        else:
            bbox_str = "(bbox unavailable)"
        count_note = (
            f" [{len(bboxes)} regions merged]" if len(bboxes) > 1 else ""
        )
        if placeholder:
            lines.append(f"- {placeholder} ({label}) at {bbox_str}{count_note}")
        else:
            lines.append(f"- [{label.upper()}] (unbound) at {bbox_str}{count_note}")
    return "\n".join(lines)


def _draw_redactions(
    image: Image.Image,
    regions: list[VisualRedactedRegion],
    *,
    padding: int = 8,
) -> Image.Image:
    """Paint redaction boxes and overlay every box with its placeholder token.

    Every box renders its placeholder (vault-bound ``<<PERSON_1>>``-style
    when available) or the canonical label fallback (``<<CUSTOMER_NAME>>``)
    so a human auditor or downstream multimodal model can identify each
    redacted region. The previous behaviour rendered the overlay on at
    most one "primary" box per token family to avoid duplicate-label
    confusion downstream, but it left adjacent boxes visually anonymous
    and made every visual demo look like the redactor "missed" the
    secondary boxes — the A2 leak eval surfaced this as a usability
    complaint. The downstream-LLM concern is now addressed at the
    prompt layer via the region-map text block (which collapses
    repeated placeholders into one), so duplicate overlay text inside
    the image is no longer a problem.
    """
    redacted = image.copy()
    draw = ImageDraw.Draw(redacted)
    width, height = redacted.size

    for region in regions:
        x1, y1, x2, y2 = region.bbox
        x1 = max(0, min(width, x1 - padding))
        y1 = max(0, min(height, y1 - padding))
        x2 = max(0, min(width, x2 + padding))
        y2 = max(0, min(height, y2 + padding))
        if x2 <= x1 or y2 <= y1:
            continue
        draw.rectangle((x1, y1, x2, y2), fill="black")
        token = region.placeholder or f"<<{region.label.upper()}>>"
        _render_box_label(draw, token, (x1, y1, x2, y2))

    return redacted


def _render_box_label(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
) -> None:
    """Render ``text`` centered inside ``box`` in white.

    The font is picked from the bundled PIL default and sized to the
    available box height. If the text overflows horizontally we
    progressively shrink the font and finally truncate with an ellipsis
    so the placeholder is at least partially visible.
    """
    x1, y1, x2, y2 = box
    box_w = x2 - x1
    box_h = y2 - y1
    if box_w < 8 or box_h < 8:
        return

    # Start with a font size that fills ~65% of the box height, shrink
    # until the text fits or we hit the bitmap floor.
    target_size = max(8, int(box_h * 0.65))
    font = _load_default_font(target_size)
    rendered = text
    while True:
        bbox = draw.textbbox((0, 0), rendered, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw <= box_w and th <= box_h:
            break
        # Try smaller font first; fall back to truncation when we
        # reach the smallest legible size.
        if target_size > 10:
            target_size -= 2
            font = _load_default_font(target_size)
            continue
        if len(rendered) <= 4:
            break
        rendered = rendered[: max(3, len(rendered) - 2)] + "…"

    bbox = draw.textbbox((0, 0), rendered, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x1 + max(0, (box_w - tw) // 2) - bbox[0]
    ty = y1 + max(0, (box_h - th) // 2) - bbox[1]
    draw.text((tx, ty), rendered, fill="white", font=font)


def _load_default_font(size: int) -> ImageFont.ImageFont:
    """Pick the best available font at *size* without leaving the process.

    PIL 10+ ships a TrueType DejaVu font that scales; older builds fall
    back to a bitmap font that ignores ``size`` — both code paths return
    something usable so redaction never crashes on a font lookup.
    """
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # PIL < 10: load_default has no size argument.
        return ImageFont.load_default()
