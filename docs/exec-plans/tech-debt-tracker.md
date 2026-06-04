# Technical Debt Tracker

This file tracks known gaps that matter to future agent runs. Keep entries
specific and delete them when resolved.

| Area | Status | Debt | Verification Needed |
| --- | --- | --- | --- |
| Documentation harness | Open | No mechanical doc freshness or cross-link checker exists yet. | Add a lightweight docs lint/check when the docs surface grows. |
| Multi-page PDF visual privacy | Open | `read_file` extracts the full multi-page text layer for digital PDFs (`_extract_pdf_text` does per-page and total character budgeting), but the scanned/image-only fallback `_render_pdf_first_page_png` still rasterises only page 1. | Add page-range parameters and tests for multi-page image-only PDF redaction before claiming full PDF coverage. |
| Visual redaction OCR dependency | Open | Image/PDF visual redaction depends on local Tesseract availability. When unavailable, visual blocks are omitted instead of sent raw. | Add startup/config diagnostics for OCR availability and a fixture-backed integration test. |
| Non-whitespace partial aliases | Open | General partial-mention scanning currently splits known `person` and `org` canonicals on whitespace. Names or organizations without whitespace token boundaries need a separate candidate strategy. | Add targeted detector tests before expanding beyond whitespace-token aliases. |
| Vault encryption | Open | Vault persistence is plaintext. | Add encrypted persistence or document why plaintext remains acceptable for local-only operation. |
| WebUI privacy side-channel | Open | The privacy side-channel ships raw PII (`SessionEntityData.value/canonical/aliases`, `WebUIToolApproval.restored_arguments`, `WebUIUserAttachment.original_data_url`, `WebUIUserDocument.original_text`); safe today only because `channels/webui.py:84` binds `127.0.0.1`. The nanobot rebase re-homes onto a channel that supports `0.0.0.0`. | Add a localhost gate + redacted projection for non-localhost connections before W2 of `exec-plans/active/nanobot-rebase.md`. |
