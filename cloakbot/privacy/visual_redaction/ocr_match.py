"""OCR text extraction, normalization, and fuzzy bbox matching.

This module owns everything between raw Tesseract output and a list of
``(label, value, bbox)`` candidates:

* the single shared ``image_to_data`` call and the word filter that turns it
  into :class:`~cloakbot.privacy.visual_redaction.models._TextWord` rows,
* text normalization / match-key helpers used to compare detector text against
  OCR tokens,
* :func:`_matching_text_word_boxes` — the strict-then-gap-tolerant fuzzy matcher
  that locates a needle's bbox(es), and
* :func:`_ocr_regex_items` — structural catches (emails, IDs, dates, amounts)
  pulled straight from the OCR stream.

Matching only paints a bbox when an OCR token literally satisfies a needle key,
so the fuzzy fallbacks here cannot trigger over-redaction beyond their pinned
window size — the conservative posture the A2 visual leak eval validated.
"""

from __future__ import annotations

import re
from typing import Any

import pytesseract
from PIL import Image

from cloakbot.privacy.visual_redaction.models import _TextWord


def normalize_ocr_text(text: str) -> str:
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


__all__ = [
    "_candidate_needles",
    "_filter_ocr_words",
    "_image_has_any_ocr_text",
    "_match_key",
    "_matching_text_word_boxes",
    "_normalize_text",
    "_ocr_data",
    "_ocr_regex_items",
    "_tokens_for_match",
    "_union_boxes",
    "normalize_ocr_text",
]
