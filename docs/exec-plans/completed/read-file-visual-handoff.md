# Read File Visual Handoff

## Goal

Keep `read_file` as the single local-file privacy boundary while allowing
privacy-sanitized image/PDF content to reach the remote model as a redacted
image plus sanitized text.

## Assumptions

- No separate `Intent.DOC` worker is being reintroduced.
- Sanitized local-file artifacts should be persisted under the privacy Vault for
  traceability and reuse within the current session/turn.
- The smallest safe integration point is the `AgentRunner` tool loop plus
  `ToolPrivacyInterceptor`.

## Steps

1. Add Vault artifact persistence helpers for sanitized file payloads -> verify:
   focused Vault tests.
2. Extend tool privacy models/interceptor to persist sanitized read-file outputs
   and queue multimodal follow-up messages -> verify:
   `tests/privacy/runtime/test_tool_interceptor.py`.
3. Teach `AgentRunner` to append interceptor-provided follow-up user messages
   after tool completion -> verify: runner tests and an end-to-end local invoice
   run.
4. Update docs to reflect the real remote boundary for text/image read-file
   content -> verify: docs mention tool-driven multimodal handoff, not a DOC
   intent.

## Decisions

- 2026-05-13: Use a synthetic post-tool user message for redacted images because
  Chat Completions tool messages cannot carry `image_url` content.

## Validation

- [x] `uv run ruff check <touched paths>`
- [x] `uv run pytest -m "not integration" tests/privacy/core/test_vault.py tests/privacy/runtime/test_tool_interceptor.py tests/agent/test_runner.py tests/tools/test_filesystem_tools.py`
- [x] Local end-to-end invoice read against `gamma4-image-test/data/invoice.jpg`
