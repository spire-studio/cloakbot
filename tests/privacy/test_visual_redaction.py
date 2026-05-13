"""Tests for the visual privacy pipeline.

Covers the two recently added behaviours:
1. Fail-closed in ``_redact_image`` — detector items unmatched OR OCR text
   present with zero redactable boxes must yield ``(None, omit_record)``.
2. ``_omitted_block`` no longer leaks the local source path into LLM-visible
   text (path is retained on the record for transparency only).
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.visual_redaction import (
    _redact_image,
    redact_visual_content_blocks,
)

# Smallest valid PNG so ``PIL.Image.open`` succeeds inside the pipeline.
_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAfbLI3wAAAABJRU5ErkJggg=="
)


def _png_data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(_TINY_PNG_BYTES).decode("ascii")


def _ocr_data_with_text(text: str = "something") -> dict[str, list]:
    """Build a Tesseract image_to_data DICT shape with one printable word."""
    return {
        "text": [text],
        "conf": [99],
        "left": [0],
        "top": [0],
        "width": [10],
        "height": [10],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "word_num": [1],
    }


def _ocr_data_empty() -> dict[str, list]:
    return {
        "text": [""],
        "conf": [-1],
        "left": [0],
        "top": [0],
        "width": [0],
        "height": [0],
        "block_num": [0],
        "par_num": [0],
        "line_num": [0],
        "word_num": [0],
    }


@pytest.mark.asyncio
async def test_redact_image_fails_closed_when_detector_items_unmatched() -> None:
    """Detector found PII but local OCR could not place a box → omit."""
    with patch(
        "cloakbot.privacy.visual_redaction._inspect_visual",
        new=AsyncMock(
            return_value={"sensitive_items": [{"label": "name", "text": "Alice"}]}
        ),
    ), patch(
        "cloakbot.privacy.visual_redaction._ocr_data",
        return_value=_ocr_data_with_text("unrelated"),
    ):
        bytes_or_none, record = await _redact_image(
            _TINY_PNG_BYTES, mime="image/png", source_path="/private/x.png"
        )

    assert bytes_or_none is None, "fail-closed must refuse to forward the image"
    assert record.status == "omitted"
    assert record.detected_items == 1
    assert record.redaction_boxes == 0
    assert "fail-closed" in (record.reason or "")
    # The source path is retained on the record (for transparency) but is the
    # caller's responsibility to keep out of LLM-visible content.
    assert record.source_path == "/private/x.png"


@pytest.mark.asyncio
async def test_redact_image_fails_closed_when_ocr_has_text_but_no_items() -> None:
    """Detector returned nothing but OCR sees text → still fail-closed.

    This is the scenario where the vLLM detector silently under-recalls
    (truncated response, malformed JSON, non-English content). Without the
    fail-closed gate the original image was forwarded as-is.
    """
    with patch(
        "cloakbot.privacy.visual_redaction._inspect_visual",
        new=AsyncMock(return_value={"sensitive_items": []}),
    ), patch(
        "cloakbot.privacy.visual_redaction._ocr_data",
        return_value=_ocr_data_with_text("hello"),
    ):
        bytes_or_none, record = await _redact_image(
            _TINY_PNG_BYTES, mime="image/png", source_path=None
        )

    assert bytes_or_none is None
    assert record.status == "omitted"


@pytest.mark.asyncio
async def test_redact_image_passes_through_when_image_has_no_text() -> None:
    """Pure photo (no OCR text, no detector items) is allowed through.

    This is the only legitimate "no boxes drawn" branch — a beach photo, a
    chart with no labels, etc. The text-presence check guards against the
    real failure mode.
    """
    with patch(
        "cloakbot.privacy.visual_redaction._inspect_visual",
        new=AsyncMock(return_value={"sensitive_items": []}),
    ), patch(
        "cloakbot.privacy.visual_redaction._ocr_data",
        return_value=_ocr_data_empty(),
    ):
        bytes_or_none, record = await _redact_image(
            _TINY_PNG_BYTES, mime="image/png", source_path=None
        )

    assert bytes_or_none is not None
    assert record.status == "redacted"
    assert record.redaction_boxes == 0


@pytest.mark.asyncio
async def test_redact_image_can_be_forced_open_via_env(monkeypatch) -> None:
    """`CLOAKBOT_VISUAL_FAIL_MODE=pass` reinstates the legacy behaviour.

    This escape hatch exists for debugging only — exercising it here keeps
    the configuration knob from silently rotting.
    """
    monkeypatch.setenv("CLOAKBOT_VISUAL_FAIL_MODE", "pass")
    with patch(
        "cloakbot.privacy.visual_redaction._inspect_visual",
        new=AsyncMock(return_value={"sensitive_items": [{"label": "name", "text": "Alice"}]}),
    ), patch(
        "cloakbot.privacy.visual_redaction._ocr_data",
        return_value=_ocr_data_with_text("unrelated"),
    ):
        bytes_or_none, record = await _redact_image(
            _TINY_PNG_BYTES, mime="image/png", source_path=None
        )

    assert bytes_or_none is not None
    assert record.status == "redacted"


@pytest.mark.asyncio
async def test_redact_visual_content_blocks_does_not_leak_source_path() -> None:
    """The omit placeholder sent to the LLM must not embed the local path.

    Regression for the path-leak via ``_omitted_block`` — the directory
    structure under ``_meta.path`` (often containing usernames or
    customer-named folders) used to surface verbatim in the model prompt.
    """
    sensitive_path = "/Users/laurie/Documents/2024_NDA_CustomerX.png"
    blocks = [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,!!!not-base64!!!"},
            "_meta": {"path": sensitive_path},
        }
    ]

    redacted, modified, records = await redact_visual_content_blocks(blocks)

    assert modified is True
    assert len(redacted) == 1
    assert redacted[0]["type"] == "text"
    assert sensitive_path not in redacted[0]["text"]
    assert "laurie" not in redacted[0]["text"].lower()
    assert "customerx" not in redacted[0]["text"].lower()
    # Path is preserved on the record for vault / transparency reporting.
    assert records[0].source_path == sensitive_path


@pytest.mark.asyncio
async def test_redact_image_records_regions_for_each_matched_box() -> None:
    """Every drawn box must show up on ``record.regions`` for the region map."""
    with patch(
        "cloakbot.privacy.visual_redaction._inspect_visual",
        new=AsyncMock(
            return_value={
                "sensitive_items": [
                    {"label": "customer_name", "text": "Alice"},
                ]
            }
        ),
    ), patch(
        "cloakbot.privacy.visual_redaction._ocr_data",
        return_value=_ocr_data_with_text("Alice"),
    ):
        bytes_or_none, record = await _redact_image(
            _TINY_PNG_BYTES, mime="image/png", source_path=None
        )

    assert bytes_or_none is not None
    assert record.regions, "regions must be populated for any matched box"
    region = record.regions[0]
    assert region.label == "customer_name"
    assert region.bbox  # non-empty bbox


@pytest.mark.asyncio
async def test_redact_image_binds_placeholders_when_resolver_is_supplied() -> None:
    """A vault-backed resolver turns matched_text into a stable placeholder.

    This is what makes the in-box token rendering usable: the same
    placeholder shown inside the redaction box also appears in the
    region-map text block, and the local restorer can swap it back to
    the original value at response time.
    """
    seen_calls: list[tuple[str, str]] = []

    def resolver(matched_text: str, label: str) -> str | None:
        seen_calls.append((matched_text, label))
        return "<<PERSON_42>>"

    with patch(
        "cloakbot.privacy.visual_redaction._inspect_visual",
        new=AsyncMock(
            return_value={
                "sensitive_items": [
                    {"label": "customer_name", "text": "Alice"},
                ]
            }
        ),
    ), patch(
        "cloakbot.privacy.visual_redaction._ocr_data",
        return_value=_ocr_data_with_text("Alice"),
    ):
        _bytes, record = await _redact_image(
            _TINY_PNG_BYTES,
            mime="image/png",
            source_path=None,
            placeholder_resolver=resolver,
        )

    assert ("Alice", "customer_name") in seen_calls
    assert record.regions[0].placeholder == "<<PERSON_42>>"


def test_format_region_map_collapses_duplicate_placeholders() -> None:
    """Two regions binding to the same placeholder must show one line.

    Regression: production-side multi-column invoices produced two
    adjacent bboxes mapped to the same ``<<ADDRESS_1>>``. The text map
    used to list both, so the downstream LLM treated them as separate
    entities and repeated the address in its reply ("…3113 Wilson
    Avenue… (Portland, Oregon 97232, US)").
    """
    from cloakbot.privacy.visual_redaction import _format_region_map_text

    regions = [
        {
            "placeholder": "<<ADDRESS_1>>",
            "label": "billing_address",
            "bbox": [120, 80, 240, 110],
        },
        {
            "placeholder": "<<ADDRESS_1>>",
            "label": "billing_address",
            "bbox": [120, 115, 260, 145],
        },
        {
            "placeholder": "<<ORG_1>>",
            "label": "vendor_name",
            "bbox": [10, 20, 80, 40],
        },
    ]
    text = _format_region_map_text(regions)
    assert text is not None
    # Exactly one bullet per unique placeholder
    bullets = [line for line in text.splitlines() if line.startswith("- ")]
    assert len(bullets) == 2
    address_line = next(line for line in bullets if "<<ADDRESS_1>>" in line)
    # The merged region must report a combined bbox spanning both
    # original boxes and flag that it represents multiple regions.
    assert "regions merged" in address_line
    assert "(120,80)" in address_line  # min corner
    assert "(260,145)" in address_line  # max corner


def test_draw_redactions_renders_each_placeholder_only_once() -> None:
    """Duplicate placeholders fill multiple boxes but the *label text* lands once."""
    from PIL import Image

    from cloakbot.privacy.visual_redaction import (
        VisualRedactedRegion,
        _draw_redactions,
    )

    image = Image.new("RGB", (400, 200), color="white")
    regions = [
        VisualRedactedRegion(
            placeholder="<<ADDRESS_1>>",
            label="billing_address",
            bbox=[10, 10, 60, 30],
        ),
        VisualRedactedRegion(
            placeholder="<<ADDRESS_1>>",
            label="billing_address",
            bbox=[10, 50, 200, 80],  # bigger — wins as primary
        ),
    ]

    rendered = _draw_redactions(image, regions)
    # We can't easily inspect "did the white pixels appear" without
    # running OCR, but we can at least confirm both bboxes have been
    # painted black. We sample the *upper-left corner* of each padded
    # bbox — text is rendered centered, so corners stay solid black
    # regardless of which box receives the placeholder label.
    pixels = rendered.load()
    assert pixels[5, 5] == (0, 0, 0)    # corner of first padded bbox
    assert pixels[5, 45] == (0, 0, 0)   # corner of second padded bbox


def test_draw_redactions_label_call_count_is_one_per_placeholder() -> None:
    from PIL import Image

    from cloakbot.privacy.visual_redaction import (
        VisualRedactedRegion,
        _draw_redactions,
    )

    image = Image.new("RGB", (400, 200), color="white")
    regions = [
        VisualRedactedRegion(
            placeholder="<<ADDRESS_1>>",
            label="billing_address",
            bbox=[10, 10, 60, 30],
        ),
        VisualRedactedRegion(
            placeholder="<<ADDRESS_1>>",
            label="billing_address",
            bbox=[10, 50, 200, 80],
        ),
        VisualRedactedRegion(
            placeholder="<<ORG_1>>",
            label="vendor_name",
            bbox=[220, 10, 360, 40],
        ),
    ]

    call_log: list[str] = []

    def fake_render(_draw, text, _box):
        call_log.append(text)

    with patch(
        "cloakbot.privacy.visual_redaction._render_box_label",
        side_effect=fake_render,
    ):
        _draw_redactions(image, regions)

    # Each distinct placeholder must produce exactly one label-render
    # call, regardless of how many bboxes it binds to.
    assert sorted(call_log) == ["<<ADDRESS_1>>", "<<ORG_1>>"]


@pytest.mark.asyncio
async def test_redact_image_uses_text_side_entities_as_visual_needles() -> None:
    """Text-side entities the multimodal model missed must still get a bbox.

    Regression for a real bug: on a multi-column invoice the visual
    detector ignored the Pay To company ("DMIT, Inc.") even though the
    text-side detector flagged it as an org. Result: OCR text was
    masked, but the image still rendered the value in plain text. The
    fix routes text-side entities into the visual matcher as
    additional needles so the bbox gets painted regardless of which
    detector first found the value.
    """
    with patch(
        "cloakbot.privacy.visual_redaction._inspect_visual",
        new=AsyncMock(return_value={"sensitive_items": []}),
    ), patch(
        "cloakbot.privacy.visual_redaction._ocr_data",
        return_value=_ocr_data_with_text("DMIT"),
    ):
        bytes_or_none, record = await _redact_image(
            _TINY_PNG_BYTES,
            mime="image/png",
            source_path=None,
            text_side_entities=[("DMIT", "org")],
        )

    assert bytes_or_none is not None
    # Even though vLLM returned no sensitive_items, the text-side
    # entity still produced a region with the correct visual label.
    assert record.regions, "expected at least one fallback region from text-side"
    region = record.regions[0]
    assert region.label == "org"
    assert region.matched_text == "DMIT"


@pytest.mark.asyncio
async def test_process_visual_blocks_back_substitutes_visual_placeholders_into_ocr_text(
    tmp_path,
) -> None:
    """OCR text must reflect placeholders that the *visual* detector allocates.

    Regression for a real bug seen in production: on a two-column
    invoice the visual detector found the customer's address (and
    rendered ``<<ADDRESS_1>>`` into the redaction box on the image),
    but the text-side detector — running on the column-jumbled OCR —
    missed it, so the OCR sanitized text still leaked the raw address
    to the remote LLM. The fix: after visual redaction allocates new
    vault placeholders, the OCR text is re-scanned via
    ``smap.replace_known_originals`` so both modalities ship the same
    redaction.
    """
    from cloakbot.privacy.core.state.vault import set_vault_workspace
    from cloakbot.privacy.visual_redaction import process_visual_blocks

    set_vault_workspace(tmp_path)

    # The OCR text contains a single line where the address sits in
    # broken column order; the upstream text-side ``sanitize_tool_output``
    # mock pretends it could not find an address here (which mirrors
    # production failure on multi-column scans).
    raw_address = "3113 Wilson Avenue, PORTLAND, Oregon, 97232"
    ocr_text = f"New York, USA {raw_address} NOTE: read terms"
    blocks = [
        {
            "type": "image_url",
            "image_url": {"url": _png_data_url()},
            "_meta": {"path": "/tmp/invoice.png"},
        }
    ]

    async def fake_sanitize(text, _session_key, *, turn_id=None):
        # Text-side detector misses the address entirely.
        return text, False, []

    async def fake_redact(_blocks, *, placeholder_resolver=None, text_side_entities=None):
        # Visual detector finds the address and allocates a placeholder
        # via the resolver — the same path the production code uses.
        placeholder = placeholder_resolver(raw_address, "billing_address")
        from cloakbot.privacy.visual_redaction import (
            VisualPrivacyRedaction,
            VisualRedactedRegion,
        )

        record = VisualPrivacyRedaction(
            sourcePath="/tmp/invoice.png",
            status="redacted",
            detectedItems=1,
            redactionBoxes=1,
            labels=["billing_address"],
            regions=[
                VisualRedactedRegion(
                    bbox=[0, 0, 10, 10],
                    label="billing_address",
                    matched_text=raw_address,
                    placeholder=placeholder,
                )
            ],
        )
        return list(_blocks), True, [record]

    # ``sanitize_tool_output`` is imported lazily inside
    # ``process_visual_blocks`` (to dodge a tool_models cycle), so
    # patch it at its source module rather than via visual_redaction.
    with patch(
        "cloakbot.privacy.visual_redaction.extract_visual_text",
        return_value=ocr_text,
    ), patch(
        "cloakbot.privacy.core.sanitization.sanitize.sanitize_tool_output",
        new=AsyncMock(side_effect=fake_sanitize),
    ), patch(
        "cloakbot.privacy.visual_redaction.redact_visual_content_blocks",
        new=AsyncMock(side_effect=fake_redact),
    ):
        result = await process_visual_blocks(
            blocks,
            session_key="cli:test",
            turn_id="turn-1",
            vault_call_id="call_x",
            persist_image=False,
            persist_ocr_text=False,
        )

    # The visual placeholder must have been back-substituted into the
    # OCR sanitized text — otherwise the OCR fallback would still
    # ship ``3113 Wilson Avenue, PORTLAND, Oregon, 97232`` to the
    # remote LLM even though the image was redacted.
    assert raw_address not in result.sanitized_text
    assert "<<ADDRESS_" in result.sanitized_text
    assert result.modified is True


@pytest.mark.asyncio
async def test_redact_visual_content_blocks_substitutes_omit_when_pipeline_fails_closed() -> None:
    """When ``_redact_image`` returns ``None`` the block must become a text omit."""
    from cloakbot.privacy.visual_redaction import VisualPrivacyRedaction

    fake_record = VisualPrivacyRedaction(
        sourcePath="/private/x.png",
        status="omitted",
        detectedItems=2,
        redactionBoxes=0,
        labels=[],
        reason="fail-closed: detector reported items but local OCR could not match any",
    )

    async def fake_redact(_raw, *, mime, source_path, placeholder_resolver=None, text_side_entities=None):
        return None, fake_record

    blocks = [
        {
            "type": "image_url",
            "image_url": {"url": _png_data_url()},
            "_meta": {"path": "/private/x.png"},
        }
    ]
    with patch(
        "cloakbot.privacy.visual_redaction._redact_image",
        side_effect=fake_redact,
    ):
        redacted, modified, records = await redact_visual_content_blocks(blocks)

    assert modified is True
    assert redacted[0]["type"] == "text"
    assert "/private/x.png" not in redacted[0]["text"]
    assert "fail-closed" in redacted[0]["text"]
    assert records == [fake_record]
