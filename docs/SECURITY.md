# Security And Privacy Invariants

The public `.github/SECURITY.md` remains the reporting and operator security guide.
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
and should update `.github/SECURITY.md`.

## Tool Boundary

Tools are classified as `local`, `external`, or `side_effect`. Sensitive values
may be restored for local execution, but non-local sensitive tool inputs require
approval. Tool outputs are sanitized before model reuse.

## Local Model Boundary

The vLLM/Ollama detector service is trusted only when it runs locally or on a
trusted private network. Do not document or implement a public detector endpoint
as safe. Detector connection settings come solely from `config.privacy.*`
(`cloakbot/providers/vllm.py`); there is no `.env` / `GEMMA_*` path.

## WebUI Privacy Side-Channel

The WebUI privacy side-channel can carry raw PII (entity values/canonicals/
aliases, restored tool arguments, original attachment bytes, original document
text). The WebSocket channel may bind `0.0.0.0`, so the bind address is **not**
the trust boundary. Only localhost connections receive the full payload;
non-localhost connections get a redacted projection via
`cloakbot/privacy/webui/side_channel.py` (`project_payload_for_egress()`), gated
in `cloakbot/webui/privacy_routes.py`. Do not widen what the side-channel emits,
or relax the localhost gate, without an explicit security decision.

## Review Triggers

Escalate security review for changes that touch:

- `cloakbot/privacy/core/state/vault.py`
- `cloakbot/privacy/runtime/tool_interceptor.py`
- `cloakbot/agent/loop.py` privacy hook placement
- provider request construction
- logging around prompts, tool calls, and restored outputs
- WebUI history persistence of privacy payloads
- `cloakbot/privacy/webui/side_channel.py` and `cloakbot/webui/privacy_routes.py`
  (side-channel egress projection + localhost gate)
- `cloakbot/channels/websocket_privacy.py` (privacy-scoped WebUI channel)
- `cloakbot/providers/vllm.py` detector endpoint resolution
