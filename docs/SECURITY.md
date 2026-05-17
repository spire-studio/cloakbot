# Security And Privacy Invariants

Root `SECURITY.md` remains the public reporting and operator security guide.
This file is the agent-facing engineering checklist.

## Do Not Leak

- Do not log raw Vault contents.
- Do not add new logs or telemetry that print raw sensitive values, restored
  tool arguments, API keys, channel tokens, or config files.
- Do not send raw user-sensitive spans to remote LLM providers.
- Do not treat WebUI privacy payloads as public telemetry; they can include
  restored display annotations and entity summaries.
- Existing local sanitizer diagnostics can include raw input/entity text for
  debugging. Treat those logs as local-sensitive data and avoid expanding that
  surface without an explicit security decision.

## Vault Handling

The Vault persists token mappings and normalized values under the configured
privacy vault directory. It is intentionally local and plaintext today. Any
change to persistence, export, sync, deletion, or retention is security-sensitive
and should update root `SECURITY.md`.

## Tool Boundary

Tools are classified as `local`, `external`, or `side_effect`. Sensitive values
may be restored for local execution, but non-local sensitive tool inputs require
approval. Tool outputs are sanitized before model reuse.

## Local Model Boundary

The vLLM/Ollama detector service is trusted only when it runs locally or on a
trusted private network. Do not document or implement a public detector endpoint
as safe.

## Review Triggers

Escalate security review for changes that touch:

- `cloakbot/privacy/core/state/vault.py`
- `cloakbot/privacy/runtime/tool_interceptor.py`
- `cloakbot/agent/loop.py` privacy hook placement
- provider request construction
- logging around prompts, tool calls, and restored outputs
- WebUI history persistence of privacy payloads
