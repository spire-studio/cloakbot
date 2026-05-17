"""Tests for the PDF text-layer fast path in ``read_file``.

The fast path is what makes a 100-page digital PDF feasible to
process: extracting the embedded text layer is milliseconds while
rasterising + OCRing each page is multiple seconds. The tests below
exercise both branches:

  * a digitally-issued PDF (selectable text) → text path
  * a PDF with no text layer (scanned image) → falls back to OCR
    rendering, which we observe by checking the result is an image-
    content-blocks list instead of a string.
"""

from __future__ import annotations

import fitz
import pytest

from cloakbot.agent.tools.filesystem import ReadFileTool


def _write_text_pdf(path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _write_image_only_pdf(path) -> None:
    # A PDF that contains a page but no inserted text. The text layer
    # is empty, so the fast path falls back to image rendering.
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


@pytest.mark.asyncio
async def test_read_file_uses_text_layer_when_pdf_is_selectable(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_text_pdf(pdf_path, "Invoice #INV-001\nCustomer: Alice")

    tool = ReadFileTool(workspace=tmp_path)
    result = await tool.execute(path=str(pdf_path))

    # Fast path returns a string with the extracted text, not an
    # image-content-blocks list. Cheaper and far more accurate than
    # OCR for digitally-issued documents.
    assert isinstance(result, str)
    assert "PDF text layer extracted" in result
    assert "Invoice #INV-001" in result
    assert "Customer: Alice" in result


@pytest.mark.asyncio
async def test_read_file_falls_back_to_image_render_for_image_only_pdf(tmp_path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    _write_image_only_pdf(pdf_path)

    tool = ReadFileTool(workspace=tmp_path)
    result = await tool.execute(path=str(pdf_path))

    # No text layer → list of content blocks containing an image,
    # which downstream visual processing will OCR.
    assert isinstance(result, list)
    assert any(
        isinstance(b, dict) and b.get("type") == "image_url" for b in result
    )
