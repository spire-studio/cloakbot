# Technical Debt Tracker

This file tracks known gaps that matter to future agent runs. Keep entries
specific and delete them when resolved.

| Area | Status | Debt | Verification Needed |
| --- | --- | --- | --- |
| Documentation harness | Open | No mechanical doc freshness or cross-link checker exists yet. | Add a lightweight docs lint/check when the docs surface grows. |
| Large document tool outputs | Open | Tool outputs are sanitized before model reuse, but large file/document results currently use the generic text sanitizer rather than chunk-aware processing. | Add chunked sanitizer tests for `read_file`/`grep` style outputs before raising file-size limits. |
| Non-whitespace partial aliases | Open | General partial-mention scanning currently splits known `person` and `org` canonicals on whitespace. Names or organizations without whitespace token boundaries need a separate candidate strategy. | Add targeted detector tests before expanding beyond whitespace-token aliases. |
| Vault encryption | Open | Vault persistence is plaintext. | Add encrypted persistence or document why plaintext remains acceptable for local-only operation. |
