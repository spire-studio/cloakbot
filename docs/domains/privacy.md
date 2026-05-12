# Privacy Domain

This is the primary domain for CloakBot. Read this before changing
`cloakbot/privacy/`, privacy-related tool handling, or WebUI privacy payloads.

## Goal

CloakBot keeps sensitive user data local while still allowing a remote LLM to
reason over sanitized structure. The remote model is treated as untrusted. It
should see placeholders, not raw sensitive values.

## Implemented Turn Flow

1. `pre_llm_hook()` calls `PrivacyRuntime.prepare_turn()`.
2. `sanitize_input_with_detection()` runs `PiiDetector`, which concurrently calls
   `GeneralPrivacyDetector` and `DigitPrivacyDetector`.
3. Before general detection, the sanitizer pre-swaps known originals and aliases
   from the session Vault, then scans known `person` and `org` canonicals for
   whitespace-token partial mentions in the current text.
4. Partial mention matches are passed to `GeneralPrivacyDetector` as user-prompt
   candidates for the local detector to judge. They are not deterministic
   post-parse injections.
5. Detected spans are rewritten as `<<ENTITY_TYPE_N>>` placeholders by the
   sanitization handler.
6. The session Vault stores placeholder identity, aliases, normalized values for
   computable entities, and local computation records.
7. `IntentAnalyzer` classifies the raw user input as `chat`, `math`, or `doc`.
8. `runtime/registry.py` maps `chat` to `ChatAgent`, `math` to `MathAgent`, and
   `doc` to `ChatAgent`.
9. The remote LLM receives only the sanitized prompt.
10. `post_llm_hook()` calls `PrivacyRuntime.finalize_turn()`.
11. Math turns execute validated snippet blocks locally, then responses are
   restored from the Vault and annotated for reports/WebUI.

## Trust Boundary

Local trusted zone:

- User input before sanitization.
- Local vLLM/Ollama detector calls.
- Vault contents and placeholder mappings.
- Local math execution.
- Tool arguments after restoration when running local tools.
- Final token restoration and WebUI privacy payload construction.

Remote or untrusted zone:

- Remote LLM providers.
- External tools and side-effecting tools.
- Any tool result that will be fed back into the model.

## Token And Vault Invariants

- Placeholder format is `<<TAG_N>>`, defined by `PLACEHOLDER_RE`.
- Placeholder indexes are stable per session and entity family.
- Known aliases are replaced before detection so multi-turn references reuse
  existing placeholders.
- Known partial-mention candidates are limited to Vault `person` and `org`
  canonical values. The current scanner splits canonicals on whitespace, skips
  one-character tokens, and only includes surfaces that appear in the current
  pre-swapped text.
- Partial-mention candidates are only detector hints. The parser still validates
  returned entities against the original text, and the downstream sanitizer only
  consumes entities returned by the detector.
- Computable placeholders store normalized values in the Vault.
- `<<CALC_N>>` placeholders represent local computation results reusable in
  later math snippets.

## Math Privacy

`MathAgent.prepare_input()` appends the privacy math instruction. The remote LLM
must emit `<python_snippet_N>result = ...</python_snippet_N>` blocks for computed
numeric answers. `core/math/math_executor.py` extracts, validates, executes, and
deduplicates these snippets locally.

The allowed snippet surface is intentionally narrow: assign an arithmetic
expression to `result`, use known numeric token names, and rely only on the
helpers allowed by `math_helpers.py`.

## Tool Privacy

The code now includes a concrete `ToolPrivacyInterceptor`:

- Tool inputs are restored before local execution.
- Non-local sensitive tool arguments trigger `ToolApprovalRequiredError`.
- Tool results are sanitized before they can be reused by the model.
- Tool records and approval requests are attached to `TurnContext` for reports
  and WebUI payloads.

Tool classes expose privacy class via `cloakbot/tool_privacy.py`:

- `local` - local-only tool behavior.
- `external` - data may leave the machine.
- `side_effect` - tool can perform side effects and needs stricter scrutiny.

When adding a tool, assign the least permissive accurate privacy class.

## Current Feature Boundaries

- Input-side sanitization is mandatory in normal turns, but the current runtime
  uses `fail_open=True` from `AgentLoop.process_message()`.
- `post_llm_hook()` restores placeholders and applies math finalization. It does
  not currently run a second LLM-response PII detector pass despite the older
  docstring wording.
- User-visible responses and WebUI display history may contain restored
  sensitive values by design. Use `sanitized_input`, WebUI `remotePrompt`, saved
  remote-history output, and privacy payloads to evaluate what crossed the
  remote model boundary.
- `Intent.DOC` is recognized but intentionally routes to `ChatAgent`; there is
  no dedicated document privacy pipeline yet.
- WebUI receives privacy snapshots, annotations, turn data, and timelines from
  `cloakbot/privacy/webui/builders.py`.

## Tests To Prefer

- `uv run pytest -m "not integration" tests/privacy/`
- `uv run pytest -m "not integration" tests/privacy/runtime/test_tool_interceptor.py`
- `uv run pytest -m "not integration" tests/privacy/core/test_math_executer.py`
- WebUI privacy changes should also run the relevant tests under
  `webui/src/features/privacy/` and `webui/src/features/chat/`.
