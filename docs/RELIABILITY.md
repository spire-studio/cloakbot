# Reliability

Reliability work should make failures observable, reproducible, and narrow.

## Local Commands

- Install dev dependencies: `uv sync --extra dev`
- Python lint used in CI: `uv run ruff check cloakbot --select F401,F841`
- Non-integration tests: `uv run pytest -m "not integration" tests/`
- Privacy tests: `uv run pytest -m "not integration" tests/privacy/`
- Optional vLLM path: `uv sync --extra vllm` then `bash scripts/start_vllm.sh`
- WebUI: from `webui/`, use `npm ci`, `npm run lint`, `npm run test`,
  `npm run build`
- Bridge: from `bridge/`, use `npm install`, `npm run build`

## CI Shape

`.github/workflows/ci.yml` is the source of truth:

- Python runs on 3.11, 3.12, and 3.13.
- Core Python CI installs `uv sync --extra dev`, runs a focused ruff check, and
  runs `pytest -m "not integration" tests/`.
- Optional integrations run on nightly/manual conditions.
- WebUI uses Node 24 and runs lint, tests, and build.
- Bridge uses Node 24 and builds.
- Docker smoke test runs `bash tests/test_docker.sh`.

## Observability

Privacy runtime events are emitted through `cloakbot/privacy/protocol/` with
trace IDs shaped as `session_key:turn_id`. Use replay helpers when investigating
turn timelines instead of inferring behavior only from logs.

Key event stages:

- `raw`
- `sanitized`
- `postprocessed`

Key event groups:

- turn received
- sanitize started/succeeded/failed
- intent classified
- dispatch started/completed/failed
- restore started/completed/failed
- turn completed

## Failure Policy

- Input sanitization currently runs fail-open from the main loop. Treat changes
  to that default as security-sensitive product behavior.
- Tool output sanitization is fail-closed inside `sanitize_tool_output()`.
- Streaming output is buffered until post-processing completes so placeholders
  are not shown mid-stream.
