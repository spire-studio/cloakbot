# Design Decisions

Key trade-offs baked into CloakBot's privacy layer. For the runtime contract see
[`../domains/privacy.md`](../domains/privacy.md); for system layout see
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).

**Redact + Tokenize, not Pseudonymize** — `<<PERSON_1>>` is simpler and safer than
replacing names with fake-but-realistic names. The remote LLM can still track
relationships between `PERSON_1` and `PERSON_2` without learning who they are.

**Two local detectors, one Vault** — CloakBot separates non-computable spans from
numeric or temporal spans so it can both preserve task structure and keep enough
normalised data locally for later math execution.

**Remote LLM as reasoning engine only for math** — math turns ask the remote model
for structure in `<python_snippet_N>` blocks; the final numeric answer is computed
locally against Vault values.

**Hook-based integration** — the privacy layer is largely isolated under
`cloakbot/privacy/` and integrates into the main runtime through `pre_llm_hook` and
`post_llm_hook`, so the upstream nanobot loop remains untouched.

**Documents are tool-sourced privacy data** — there is no separate document worker;
the same chunker-backed sanitiser path serves `read_file`, `web_fetch`, MCP tool
results, and WebUI document uploads. One trust boundary, one Vault.
