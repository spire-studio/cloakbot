# CloakBot privacy eval

End-to-end leak evaluation for the privacy pipeline. The goal of this corpus is
to answer one question per run: **did any ground-truth sensitive value leak
into the payload that would have been sent upstream?**

## Why this layout

Templates declare slots (Faker calls or fixed choices) and reference them in a
multi-turn dialogue. The filler realises slot values **once per session** so
the same name appears across turns — which is exactly the property
`alias_consistency_across_turns` measures.

GPT is used **only** to paraphrase template text. Slot tokens (`{patient}`,
`{phone}`, …) are preserved by GPT and filled later by Faker. Ground truth is
therefore always Faker-derived, never GPT-derived — leaks are detected by
literal substring match, with no model in the grading loop.

## Layout

```
tests/eval/
├── templates/
│   ├── *.yaml                       A1 short-dialogue scenarios
│   └── long/*.yaml                  A3 long-document scenarios
├── generators/
│   ├── faker_filler.py              slot realisation + session rendering
│   ├── paraphrase_with_gpt.py       A1: short-dialogue variants
│   ├── paraphrase_long_with_gpt.py  A3: long-document variants (slot-preserving expansion)
│   └── render_invoice.py            A2: programmatic invoice renderer (visual eval)
├── runners/
│   ├── text_leak_eval.py            A1: prepare_turn / user-input path
│   ├── visual_leak_eval.py          A2: redact_visual_content_blocks + re-OCR
│   └── long_doc_leak_eval.py        A3: sanitize_tool_output_chunked / tool path + chunker
├── corpus/generated/                .gitignored; regenerated from templates + seeds
└── reports/                         per-run summaries + gpt_audit.jsonl
```

## Quickstart

```bash
uv sync --extra eval

# A1 — short multi-turn dialogue, user-input path
uv run python -m tests.eval.generators.paraphrase_with_gpt \
    tests/eval/templates/medical_followup_v1.yaml --variants 5 \
    --out tests/eval/corpus/generated/medical_followup_v1.paraphrased.yaml
uv run python -m tests.eval.runners.text_leak_eval \
    --template tests/eval/templates/medical_followup_v1.yaml \
    --paraphrased tests/eval/corpus/generated/medical_followup_v1.paraphrased.yaml

# A2 — visual eval (no vLLM call required; bbox + re-OCR scoring)
uv run python -m tests.eval.runners.visual_leak_eval

# A3 — long-document via tool-output (chunker-backed) path
uv run python -m tests.eval.generators.paraphrase_long_with_gpt \
    tests/eval/templates/long/long_legal_correspondence_v1.yaml --variants 5 \
    --out tests/eval/corpus/generated/long_legal_correspondence_v1.paraphrased.yaml
uv run python -m tests.eval.runners.long_doc_leak_eval \
    --template tests/eval/templates/long/long_legal_correspondence_v1.yaml \
    --paraphrased tests/eval/corpus/generated/long_legal_correspondence_v1.paraphrased.yaml
```

## A3 long-document eval — what it adds on top of A1

A1 drives short user turns through `PrivacyRuntime.prepare_turn`, which
never exercises the chunker — inputs under ~6000 characters take the
single-shot detector path. A3 targets the **tool-output path** where
long documents actually live in CloakBot's contract: a tool returns a
long payload (`read_file`, fetch, search result, …), the interceptor
routes it through `sanitize_tool_output_chunked`, and the chunker splits
the payload into ~6000-char windows before per-chunk PII detection.

A3 reports the A1 metric set **plus**:

- `n_chunker_activated` — sessions where the long doc split into ≥2
  chunks (i.e. the chunker actually ran multi-window detection).
- `seam_leaks` / `seam_leaks_within_overlap` — for every leaked
  identifying token, its char offset and distance to the nearest chunk
  seam. Leaks inside the overlap band signal an overlap-window failure;
  leaks deep inside a chunk signal a per-chunk detection miss.
- `cross_path_alias_rate` — fraction of entities that get the same
  placeholder on the tool-output path **and** on the prepare_turn path,
  i.e. the vault carries the entity across the tool→input boundary.

## Metrics

| Name | What it answers | Where reported |
|---|---|---|
| `pair_leak_rate` | Any identifying token from an entity reached prepared text | A1, A3 |
| `token_leak_rate` | Fraction of identifying tokens that escaped | A1, A2, A3 |
| `per_type_recall` | Per-entity-type masking recall (pair + token) | A1, A3 |
| `alias_consistency_across_turns` | Same original → same placeholder across turns | A1, A3 |
| `n_chunker_activated` | Long docs that triggered multi-chunk detection | A3 |
| `seam_leaks_within_overlap` | Leaks attributable to chunk seam overlap failure | A3 |
| `cross_path_alias_rate` | Vault carryover from tool-output to prepare_turn | A3 |
| `p95_turn_latency_ms` | Per-stage latency at p95 | A1, A3 |
