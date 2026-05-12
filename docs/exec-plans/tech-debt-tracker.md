# Technical Debt Tracker

This file tracks known gaps that matter to future agent runs. Keep entries
specific and delete them when resolved.

| Area | Status | Debt | Verification Needed |
| --- | --- | --- | --- |
| Documentation harness | Open | No mechanical doc freshness or cross-link checker exists yet. | Add a lightweight docs lint/check when the docs surface grows. |
| Document privacy | Open | `Intent.DOC` routes to `ChatAgent`; no dedicated document/dataset privacy pipeline exists. | Add tests and docs when a real `DocAgent` or chunk-map-aggregate flow lands. |
| Response-side detection | Open | `post_llm_hook()` restores and reports but does not run a second detector pass on LLM output. | Decide whether response detection is required, then test the chosen policy. |
| Non-whitespace partial aliases | Open | General partial-mention scanning currently splits known `person` and `org` canonicals on whitespace. Names or organizations without whitespace token boundaries need a separate candidate strategy. | Add targeted detector tests before expanding beyond whitespace-token aliases. |
| Vault encryption | Open | Vault persistence is plaintext. | Add encrypted persistence or document why plaintext remains acceptable for local-only operation. |
| Visual regression | Open | WebUI privacy panel has component tests but no automated screenshot workflow. | Add browser-based checks for key privacy states if UI churn continues. |
