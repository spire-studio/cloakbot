"""Region-map text rendering and PIL redaction-box drawing.

Two presentation concerns, both fed by the same
:class:`~cloakbot.privacy.visual_redaction.models.VisualRedactedRegion` list:

* :func:`_draw_redactions` paints an opaque box over each region and overlays
  its placeholder token (``<<PERSON_1>>``) or label fallback in white.
* :func:`_format_region_map_text` renders the sibling text block that lists each
  ``placeholder → label + bbox`` once, so text-mostly models can reference a
  redacted region by token.

Neither function ever emits the original PII value — only the placeholder token
or the canonical label. The textual map is what lets the local restorer swap the
token back to the real value in the user-facing reply.
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw, ImageFont

from cloakbot.privacy.visual_redaction.models import VisualRedactedRegion


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


__all__ = [
    "_draw_redactions",
    "_format_region_map_text",
    "_load_default_font",
    "_render_box_label",
]
