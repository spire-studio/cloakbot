"""Deterministic invoice renderer for the A2 visual leak eval.

Renders a synthetic invoice PNG from a Faker-driven slot set and returns
ground-truth bboxes for every PII span we drew. The eval runner then
treats the GT spans as "what the detector should have caught" and asks:
after we paint the redaction boxes, does any GT token survive a re-OCR
pass on the redacted image?

Why this exists separately from the production `visual_redaction.py`:
the production pipeline needs a live vLLM client to call the multimodal
detector. For an offline, reproducible eval we want a path that depends
only on Faker + PIL + Tesseract, so the grading loop is closed and the
numbers can be rerun on a laptop without network.

Layout choices are intentionally boring (left-aligned, 14pt body, no
fancy typography) so Tesseract can OCR the result reliably — otherwise
the residual-leak signal would be polluted by OCR noise instead of
genuine redaction misses.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from faker import Faker
from PIL import Image, ImageDraw, ImageFont

CANVAS_SIZE = (1240, 1600)
MARGIN = 60
LINE_SPACING = 8


@dataclass(frozen=True)
class GroundTruthSpan:
    """A piece of PII we deliberately rendered, with its on-canvas bbox.

    ``text`` is the literal string painted on the canvas. ``label`` uses
    the visual-pipeline vocabulary so the runner can feed the GT directly
    into ``text_side_entities`` and the redaction call sees the same
    label names downstream consumers expect.
    """

    text: str
    label: str
    entity_type: str  # text-side privacy registry tag, for cross-modal routing
    bbox: list[int]  # [x1, y1, x2, y2]


@dataclass
class RenderedInvoice:
    seed: int
    template_id: str
    image_bytes: bytes
    width: int
    height: int
    spans: list[GroundTruthSpan] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "template_id": self.template_id,
            "width": self.width,
            "height": self.height,
            "spans": [asdict(span) for span in self.spans],
        }


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best-effort TrueType font lookup; falls back to PIL's bitmap font.

    Bigger sizes are essential for the OCR signal to stay clean — at the
    bitmap-font fallback size, even unredacted text barely OCRs, which
    would muddy the residual-leak metric.
    """
    candidates_regular = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    candidates_bold = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    pool = candidates_bold if bold else candidates_regular
    for path in pool:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: Any) -> list[int]:
    bbox = draw.textbbox(xy, text, font=font)
    return [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]


def _draw_field(
    draw: ImageDraw.ImageDraw,
    *,
    xy: tuple[int, int],
    label: str,
    value: str,
    font_label: Any,
    font_value: Any,
) -> list[int]:
    """Draw a `Label: value` row and return the bbox of ``value`` only.

    Only the value carries PII, so the GT bbox excludes the label so the
    runner doesn't accidentally also try to redact the field name.
    """
    label_text = f"{label}: "
    draw.text(xy, label_text, fill="black", font=font_label)
    label_bbox = draw.textbbox(xy, label_text, font=font_label)
    value_x = label_bbox[2] + 6
    value_y = xy[1]
    draw.text((value_x, value_y), value, fill="black", font=font_value)
    return _text_box(draw, (value_x, value_y), value, font_value)


def render_invoice_v1(seed: int, *, locale: str = "en_US") -> RenderedInvoice:
    """Render a single A2 evaluation invoice deterministically from ``seed``.

    The layout is fixed — only the slot values change — so per-seed
    visual diffs reveal redaction differences cleanly. Boxes returned in
    GT have ``label`` values aligned with the visual-pipeline vocabulary
    (``customer_name`` / ``billing_address`` / ``transaction_id`` / etc.)
    so the runner can hand them straight to the redaction call.
    """
    faker = Faker(locale)
    faker.seed_instance(seed)

    width, height = CANVAS_SIZE
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    f_title = _load_font(36, bold=True)
    f_h2 = _load_font(20, bold=True)
    f_label = _load_font(15)
    f_value = _load_font(17, bold=True)
    f_body = _load_font(15)

    spans: list[GroundTruthSpan] = []

    # ----- Header band ---------------------------------------------------
    draw.text((MARGIN, MARGIN), "INVOICE", fill="black", font=f_title)
    draw.rectangle((MARGIN, MARGIN + 60, width - MARGIN, MARGIN + 62), fill="black")

    cursor_y = MARGIN + 80

    # ----- Vendor block (top right) -------------------------------------
    vendor_name = faker.company()
    vendor_address = faker.address().replace("\n", ", ")
    vendor_email = faker.company_email()

    right_x = width - MARGIN - 480
    draw.text((right_x, cursor_y), "Issued by", fill="#444", font=f_label)
    bbox = _text_box(draw, (right_x, cursor_y + 24), vendor_name, f_value)
    draw.text((right_x, cursor_y + 24), vendor_name, fill="black", font=f_value)
    spans.append(GroundTruthSpan(text=vendor_name, label="vendor_name", entity_type="org", bbox=bbox))

    bbox = _text_box(draw, (right_x, cursor_y + 52), vendor_address, f_body)
    draw.text((right_x, cursor_y + 52), vendor_address, fill="black", font=f_body)
    spans.append(GroundTruthSpan(text=vendor_address, label="billing_address", entity_type="address", bbox=bbox))

    bbox = _text_box(draw, (right_x, cursor_y + 76), vendor_email, f_body)
    draw.text((right_x, cursor_y + 76), vendor_email, fill="black", font=f_body)
    spans.append(GroundTruthSpan(text=vendor_email, label="email", entity_type="email", bbox=bbox))

    # ----- Bill-to block (top left) -------------------------------------
    customer_name = faker.name()
    customer_address = faker.address().replace("\n", ", ")
    customer_phone = f"+1 ({faker.numerify('###')}) {faker.numerify('###')}-{faker.numerify('####')}"
    customer_email = faker.email()

    draw.text((MARGIN, cursor_y), "Billed to", fill="#444", font=f_label)
    bbox = _text_box(draw, (MARGIN, cursor_y + 24), customer_name, f_value)
    draw.text((MARGIN, cursor_y + 24), customer_name, fill="black", font=f_value)
    spans.append(GroundTruthSpan(text=customer_name, label="customer_name", entity_type="person", bbox=bbox))

    bbox = _text_box(draw, (MARGIN, cursor_y + 52), customer_address, f_body)
    draw.text((MARGIN, cursor_y + 52), customer_address, fill="black", font=f_body)
    spans.append(GroundTruthSpan(text=customer_address, label="billing_address", entity_type="address", bbox=bbox))

    bbox = _text_box(draw, (MARGIN, cursor_y + 76), customer_phone, f_body)
    draw.text((MARGIN, cursor_y + 76), customer_phone, fill="black", font=f_body)
    spans.append(GroundTruthSpan(text=customer_phone, label="phone", entity_type="phone", bbox=bbox))

    bbox = _text_box(draw, (MARGIN, cursor_y + 100), customer_email, f_body)
    draw.text((MARGIN, cursor_y + 100), customer_email, fill="black", font=f_body)
    spans.append(GroundTruthSpan(text=customer_email, label="email", entity_type="email", bbox=bbox))

    cursor_y += 180

    # ----- Invoice metadata strip ---------------------------------------
    draw.rectangle(
        (MARGIN, cursor_y, width - MARGIN, cursor_y + 90),
        fill="#f4f1ea",
        outline="#d4d0c2",
        width=1,
    )

    meta_y = cursor_y + 14
    col_step = (width - 2 * MARGIN) // 3

    invoice_number = f"INV-{faker.numerify('####')}-{faker.bothify('?#?#').upper()}"
    issued_at = faker.date_between(start_date="-90d", end_date="-15d").strftime("%Y-%m-%d")
    due_at = faker.date_between(start_date="+1d", end_date="+30d").strftime("%Y-%m-%d")

    for col_index, (label, value, label_name, entity_type) in enumerate(
        [
            ("Invoice #", invoice_number, "invoice_number", "identifier"),
            ("Issue date", issued_at, "date", "temporal"),
            ("Due date", due_at, "date", "temporal"),
        ]
    ):
        x = MARGIN + 14 + col_index * col_step
        draw.text((x, meta_y), label, fill="#555", font=f_label)
        bbox = _text_box(draw, (x, meta_y + 24), value, f_value)
        draw.text((x, meta_y + 24), value, fill="black", font=f_value)
        spans.append(GroundTruthSpan(text=value, label=label_name, entity_type=entity_type, bbox=bbox))

    cursor_y += 120

    # ----- Line items ---------------------------------------------------
    draw.text((MARGIN, cursor_y), "Line items", fill="black", font=f_h2)
    cursor_y += 32
    draw.line((MARGIN, cursor_y, width - MARGIN, cursor_y), fill="#bbb", width=1)
    cursor_y += 10

    # Line item descriptions are intentionally non-PII fixed strings: the
    # A2 lite scope is "does redaction of labeled fields survive re-OCR?"
    # and a Faker-filled description (job title, city name, company
    # suffix) would smuggle un-tracked PII into the canvas and give the
    # eval a false-clean signal. Keep these generic; the slot-level
    # contract stays clean.
    descriptions = [
        "Consulting services",
        "Engineering hours",
        "Software licenses",
        "Travel expense",
    ]
    line_total = 0.0
    for description in descriptions:
        amount = round(faker.pyfloat(left_digits=4, right_digits=2, positive=True, min_value=300, max_value=4800), 2)
        line_total += amount
        amount_text = f"${amount:,.2f}"
        draw.text((MARGIN, cursor_y), description, fill="black", font=f_body)
        amount_bbox = _text_box(draw, (width - MARGIN - 140, cursor_y), amount_text, f_value)
        draw.text((width - MARGIN - 140, cursor_y), amount_text, fill="black", font=f_value)
        spans.append(GroundTruthSpan(text=amount_text, label="amount", entity_type="financial", bbox=amount_bbox))
        cursor_y += 36

    cursor_y += 12
    draw.line((MARGIN, cursor_y, width - MARGIN, cursor_y), fill="#bbb", width=1)
    cursor_y += 18

    # ----- Totals & payment ---------------------------------------------
    total_text = f"${line_total:,.2f}"
    draw.text((width - MARGIN - 260, cursor_y), "Total due", fill="black", font=f_h2)
    bbox = _text_box(draw, (width - MARGIN - 140, cursor_y), total_text, f_value)
    draw.text((width - MARGIN - 140, cursor_y), total_text, fill="black", font=f_value)
    spans.append(GroundTruthSpan(text=total_text, label="amount", entity_type="financial", bbox=bbox))

    cursor_y += 70

    card_brand = faker.random_element(["Amex", "Visa", "Mastercard"])
    card_last4 = faker.numerify("####")
    transaction_id = faker.bothify("TXN-#?#?-########?????").upper()
    account_iban = faker.bothify("US## #### #### ####").upper()

    draw.text((MARGIN, cursor_y), "Payment details", fill="black", font=f_h2)
    cursor_y += 32

    bbox = _draw_field(
        draw,
        xy=(MARGIN, cursor_y),
        label="Card",
        value=f"{card_brand} ending {card_last4}",
        font_label=f_label,
        font_value=f_value,
    )
    spans.append(
        GroundTruthSpan(
            text=f"{card_brand} ending {card_last4}",
            label="account_number",
            entity_type="identifier",
            bbox=bbox,
        )
    )
    cursor_y += 36

    bbox = _draw_field(
        draw,
        xy=(MARGIN, cursor_y),
        label="Account",
        value=account_iban,
        font_label=f_label,
        font_value=f_value,
    )
    spans.append(GroundTruthSpan(text=account_iban, label="account_number", entity_type="identifier", bbox=bbox))
    cursor_y += 36

    bbox = _draw_field(
        draw,
        xy=(MARGIN, cursor_y),
        label="Transaction",
        value=transaction_id,
        font_label=f_label,
        font_value=f_value,
    )
    spans.append(
        GroundTruthSpan(text=transaction_id, label="transaction_id", entity_type="identifier", bbox=bbox)
    )
    cursor_y += 60

    # ----- Footer note --------------------------------------------------
    footer_note = (
        f"Questions? Reach the billing team at {vendor_email} or call "
        f"{customer_phone} during business hours."
    )
    draw.text((MARGIN, cursor_y), footer_note, fill="#555", font=f_body)

    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return RenderedInvoice(
        seed=seed,
        template_id="invoice_v1",
        image_bytes=buffer.getvalue(),
        width=width,
        height=height,
        spans=spans,
    )


def save_rendered_invoice(invoice: RenderedInvoice, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{invoice.template_id}.seed{invoice.seed:04d}.png"
    path.write_bytes(invoice.image_bytes)
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render a single A2 invoice for inspection.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/eval/corpus/generated/visual"),
    )
    args = parser.parse_args()

    invoice = render_invoice_v1(args.seed)
    path = save_rendered_invoice(invoice, args.out)
    print(f"wrote {path} ({len(invoice.spans)} GT spans)")
