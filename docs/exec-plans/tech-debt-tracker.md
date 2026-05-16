# Technical Debt Tracker

This file tracks known gaps that matter to future agent runs. Keep entries
specific and delete them when resolved.

| Area | Status | Debt | Verification Needed |
| --- | --- | --- | --- |
| Documentation harness | Open | No mechanical doc freshness or cross-link checker exists yet. | Add a lightweight docs lint/check when the docs surface grows. |
| Multi-page PDF visual privacy | Open | `read_file` currently renders the first PDF page for visual privacy; multi-page document coverage still needs pagination semantics and output budgeting. | Add page-range parameters and tests for multi-page PDF redaction before claiming full PDF coverage. |
| Visual redaction OCR dependency | Open | Image/PDF visual redaction depends on local Tesseract availability. When unavailable, visual blocks are omitted instead of sent raw. | Add startup/config diagnostics for OCR availability and a fixture-backed integration test. |
| Non-whitespace partial aliases | Open | General partial-mention scanning currently splits known `person` and `org` canonicals on whitespace. Names or organizations without whitespace token boundaries need a separate candidate strategy. | Add targeted detector tests before expanding beyond whitespace-token aliases. |
| Vault encryption | Open | Vault persistence is plaintext. | Add encrypted persistence or document why plaintext remains acceptable for local-only operation. |
