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
├── templates/                 hand-authored YAML scenarios
├── generators/
│   ├── faker_filler.py        slot realisation + session rendering
│   └── paraphrase_with_gpt.py GPT-driven natural-prose variants
├── runners/                   (next: text_leak_eval.py, visual_leak_eval.py)
├── corpus/generated/          .gitignored; regenerated from templates + seeds
└── reports/                   per-run summaries + gpt_audit.jsonl
```

## Quickstart

```bash
uv sync --extra eval

# 1. See what a template realises as
uv run python -m tests.eval.generators.faker_filler \
    tests/eval/templates/medical_followup_v1.yaml

# 2. Paraphrase one template into N natural variants (uses .env)
uv run python -m tests.eval.generators.paraphrase_with_gpt \
    tests/eval/templates/medical_followup_v1.yaml --variants 5
```

## Metrics (planned)

| Name | What it answers |
|---|---|
| `leak_count` | How many ground-truth values appeared in the outgoing payload |
| `per_type_recall` | Per-entity-type masking recall |
| `alias_consistency_across_turns` | Same original → same placeholder across turns |
| `vault_carryover_hit_rate` | Turn N reuses placeholder from turn 1 |
| `p95_latency_ms` | Per-stage latency at p95 |
