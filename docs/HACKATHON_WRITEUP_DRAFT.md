# CloakBot — A Local Privacy Kernel for Frontier LLMs

*Gemma 4 E2B privacy kernel · Safety & Trust · Main Track + Ollama Special Tech · 2,872 entity-test receipts.*

---

## TL;DR

Frontier LLM use is now load-bearing — but the data that crosses the wire is non-revocable. CloakBot moves enforcement **before the wire**: a **local privacy kernel** on Gemma 4 E2B that detects sensitive spans, assigns typed aliases, redacts images, chunks long documents, and restores outputs from a per-session vault. **The remote LLM is interchangeable** — Claude, GPT, and Gemini all accept the sanitised stream unchanged. **Gemma 4 is the trust layer.**

Backed by **2,872 entity-test receipts** across three end-to-end leak-eval layers — methodology, per-layer numbers, and self-caught harness bugs in §4 and §5. Reproduces from one command.

---

## §1 The story I keep returning to

David runs a one-person wealth advisory. His client — a 64-year-old widow — trusts him with $812,000 of retirement savings. It's Friday; the quarterly statement is due Monday.

He pastes the statement into Claude: *"Draft a friendly summary for my client."* Claude returns a beautifully empathic paragraph. He sends it. The client cries with gratitude.

She does not know that her name, birth date, account number, cost-basis schedule, and unrealised gains are now indexed in a foreign-jurisdiction inference cluster she has no contract with. David does not know either. No log, no receipt, no deletion path.

Not a personal failure — a *structural* one. Deletion, opt-outs, audit logs all happen **after** the wire. The fix has to be earlier — on hardware David controls, **before** the wire. That's CloakBot.

---

## §2 What CloakBot does

```
David's screen                              Remote LLM sees
──────────────                              ──────────────
"Draft a summary for Marilyn Carter,        "Draft a summary for <<PERSON_1>>,
 age 64, account 4471-08-2934, with          age <<NUMBER_1>>, account <<ID_1>>,
 unrealised gains of $58,420 …"              with unrealised gains of <<FINANCE_1>> …"

         ▲                                          ▲
         │                                          │
    PrivacyRuntime  ◄─── Gemma 4 E2B detectors ───► (over network)
         │                                          │
   Session Vault  ◄────  restored locally  ◄────────┘
```

Sensitive spans become typed placeholders before the remote LLM sees the request. Math snippets compute locally on raw values — the remote model only assembles the formula. Image uploads are OCR'd, sanitised, and redacted in-place with placeholder text overlaid on each black bar. Long documents are chunked, sanitised per chunk, then re-assembled with cross-chunk vault coalescing — same `<<PERSON_1>>` across chunks. None of this requires the remote model's cooperation — the boundary is enforced unilaterally.

---

## §3 Why Gemma 4 — and not regex or BERT-NER

CloakBot uses regex on the **fast path**: emails, invoice numbers, transaction IDs, file paths — hand-rolled in `privacy/core/detection/`. We keep that. What regex and BERT-NER *cannot* do is the other 80%:

| Failure mode | Regex | BERT-NER | Gemma 4 E2B |
|---|:---:|:---:|:---:|
| Known formats (email, SSN, card) | ✓ | ✓ | ✓ |
| Disambiguate "John" placeholder vs real customer | ✗ | ✗ | ✓ |
| Instructional numbers (`give me 3 bullet points`) | tokenizes `3` | varies | kept as task structure |
| Combination identifiers (ZIP + age + diagnosis) | ✗ | ✗ | ✓ |
| Cross-turn dedupe (`someone else surnamed Lin` ≠ PERSON_1) | n/a | n/a | emits `new`, not the placeholder |
| Add a new entity (`codename Falcon`) | edit regex | retrain | edit prompt |
| Multilingual (CN/JP/KR) on one model | ✗ | 600 MB+/locale | ✓ |
| Computable normalization (`$1,200.50` → `1200.5`, `15%` → `0.15`) | string-only | string-only | typed numeric, runs in `<python_snippet>` |

A *PII proxy that catches the easy stuff* is **worse than no proxy**, because users trust it. Pre-wire enforcement reasons about context, not patterns. Gemma 4 E2B is the only redistributable model that fits on David's MacBook *and* answers *"should this token be redacted **in this conversation**?"* — ~5 GB, JSON-at-T=0, native vision, Gemma license.

**vLLM for reproducible evals; Ollama for adoption.** `ollama pull gemma:e2b` ships the model + OpenAI-compatible endpoint in one tool. **Gemma 4 is the trust layer; Ollama is the deployment layer.**

---

## §4 Trust by measurement — three layers

Our harness answers one question per run: **did any ground-truth identifying token reach the upstream payload?** GPT paraphrases templates into 5 variants; Faker realises slots from fixed seeds (the ground truth); leak detection is literal substring matching. **GPT is not in the grading loop.** *Pair leak* = any token leaked; *token leak* = fraction that escaped.

**A1 — text input, 4 domains × 20 sessions × 902 entity-turn pairs:**

| Domain | Pair leak | Token leak | Alias | p95 (ms) |
|---|---:|---:|---:|---:|
| Medical | **2.22%** | 2.44% | **95.00%** | 6,224 |
| Finance | 7.19% | 5.64% | **100.00%** | 5,937 |
| HR | 9.82% | 8.41% | n/a | 900 |
| Customer service | 12.90% | 6.15% | n/a | 5,822 |
| **Cross-domain** | **7.98%** | **5.88%** | **97.14%** | 6,224 |

Per-type: 100% on EMAIL/PHONE/FINANCE/IP/URL · 96.88% PERSON · **95% MEDICAL** (from a 20% baseline — see §5). Medical buys accuracy with latency: entity density triggers detector concurrency.

**A2 — visual, 10 invoice seeds × 180 PII spans:** **span leak 1.11%** after redact + re-OCR; placeholder text rendered *inside* each black bar. 8/10 label categories at 0% leak.

**A3 — long-document chunker, 3 domains × 1,790 pairs:** **pair leak 6.26%, cross-path alias 93.86%** (the `<<PERSON_1>>` from chunking carries to David's follow-up turn). **0/226 seam leaks** in the 300-char overlap band — every long-doc leak is an intra-chunk miss, never a seam dropout. Best template (`long_email_v1`): **1.15% token leak, 100% cross-path alias**.

> *p95 latency measured with Gemma 4 E2B on an RTX 5090 (vLLM); MacBook (Ollama) runs end-to-end but slower — MacBook is the deployment target, not the measurement rig.*

---

## §5 The eval evaluates the eval

The harness has caught two of its own bugs — both silently inflated recall, both had to be fixed before any detector iteration mattered:

- **v1** scored leaks by full-value substring. `Garcia Light, West Melanieview, AS` looked like 100% recall because two ZIP digits were masked even though the alphabetic body was naked. Switched to token-level.
- **v2** counted "entity appears in turn N" by any-token overlap, so surname collisions (`Johnson` in person + company) faked multi-turn recurrence. Tightened appearance to full-value, kept leak detection at token level.

Detector iteration was *type-driven*, not *rule-driven*. v1 added four prompt rules (*"medications with dosages → MEDICAL"*); MEDICAL recall stayed at 20%. v2 deleted the rules and put the same info into `EntitySpec(medical).examples` as concrete strings; recall jumped to 95%. **Small models lean on examples better than rule lists.** The v2 ORG/ID rebalance lifted cross-domain alias 93.94% → 97.14% while shaving ~150 prompt tokens.

---

## §6 The multi-agent shape *is* the enterprise blueprint

CloakBot isn't "five small tools" — it's what institution-scale AI privacy architecture has to look like:

```
                Per turn (input → response)
                          │
                 ┌────────▼────────┐
                 │  PrivacyRuntime │  ◄── coordinator + audit
                 └────────┬────────┘
                          │
       ┌──────────┬───────┴───────┬─────────────┐
       ▼          ▼               ▼             ▼
  PiiDetector  ToolPrivacy   VisualPrivacy   DocChunker
    (input)    Interceptor      Pipeline      (long docs)
               (tool I/O)       (images)
       │          │               │             │
       └──────────┴───────┬───────┴─────────────┘
                          ▼
                 ┌────────────────┐
                 │ Session Vault  │  ◄── per-session, on disk
                 │ audit-traceable│      placeholder ↔ raw
                 └────────────────┘
```

Compliance falls out: the per-session vault *is* **GDPR Article 17's** deletion path; **HIPAA-aligned** because raw PHI never crosses the local boundary. **Same architecture a bank, clinic, or law firm needs — demoed on David's laptop.**

---

## §7 What's left honest

- **ORG short / hyphenated names**: 71.67% pair recall — largest A1 gap.
- **Weekday dates** (*"Friday at 3:21 PM"*): 84% — Gemma 4 treats weekday as generic.
- Long medical phrases (`stage 2 chronic kidney disease`) slip occasionally.
- A2 residual: 3 leaks across 10 invoices — `Turner Ltd` + OCR noise on 2 emails.
- **Latency**: Medical p95 6.2s (entity-dense concurrency); HR p95 0.9s. Streaming + batching is next.
- Sub-3% PERSON/DATE variance isn't reproducible — Gemma 4 E2B isn't bit-deterministic at T=0; treated as intrinsic noise.

---

## §8 Reproducibility

Public repo: [`github.com/spire-studio/cloakbot`](https://github.com/spire-studio/cloakbot). Setup follows the README's *Setup* section — `uv sync`, pick a Gemma 4 backend (vLLM or Ollama), launch the WebUI. The three eval layers (A1 / A2 / A3) reproduce from `tests/eval/runners/`; audit log and A/B snapshots live under `tests/eval/reports/`.

---

## §9 Why this matters now

*"Don't be evil"* was a motto. In 2026, ***can't see evil* has to be an architecture.** The data that crosses the wire is non-revocable; the only durable fix is to move enforcement **before the wire** — local, auditable, measurable, independent of the remote model's cooperation.

We built that kernel on Gemma 4 E2B, fit it on a MacBook through Ollama, and backed it with 2,872 entity-test instances of receipts. Open-source — the architecture David runs tonight is what a Fortune 500 can harden, audit, deploy.

Privacy-by-construction, 2026.

---

*— Built by [Laurie Luo](mailto:me@laurie.pro) for the Gemma 4 Good Hackathon, May 2026.*
