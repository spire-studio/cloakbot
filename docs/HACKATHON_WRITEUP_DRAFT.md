# CloakBot — A Local Privacy Kernel for Frontier LLMs

*A Gemma 4 E2B privacy kernel for **Safety & Trust** — measurable pre-wire enforcement, 2,872 entity-test instances of receipts.*
*The Gemma 4 Good Hackathon — Main Track · Ollama Special Technology.*

---

## TL;DR

Frontier LLM use is now load-bearing — but the data that crosses the wire is non-revocable. CloakBot moves enforcement **before the wire**: a **local privacy kernel** on Gemma 4 E2B that detects sensitive spans, assigns stable typed aliases, redacts images, chunks long documents, and restores outputs locally from a per-session vault. **The remote LLM is interchangeable** — Claude, GPT, and Gemini all accept the sanitised stream unchanged. **Gemma 4 is the trust layer.**

Three layers of end-to-end leak eval — **2,872 entity-test instances** across pair-level (text) and span-level (visual):

- **A1 (text input)** — 80 sessions × 4 domains × 902 pairs → **7.98% pair leak, 5.88% token leak, 97.14% alias consistency**.
- **A2 (visual)** — 10 invoices × 180 PII spans → **1.11% span leak, 1.01% token leak** after redact + re-OCR.
- **A3 (long-document)** — 60 sessions × 3 domains × 1,790 pairs through the chunker → **6.26% pair leak, 93.86% cross-path alias, 0 of 226 seam leaks within the 300-char overlap band**.
- **100% pair recall** cross-domain on **EMAIL · PHONE · FINANCE · IP · URL** — the literal user-typed types.
- **MEDICAL recall: 20% → 95%** via type-driven prompt iteration (§5).

Reproduces from one command.

---

## §1 The story I keep returning to

David runs a one-person wealth advisory practice. His client — a 64-year-old widow — trusts him with $812,000 of retirement savings. It's Friday. The quarterly statement is due Monday.

He pastes the statement into Claude: *"Draft a friendly summary for my client."* Claude returns a beautifully empathic paragraph. He sends it. The client cries with gratitude.

She does not know that her name, her birth date, her account number, her cost-basis schedule, and her unrealised gains for the year are now indexed in a foreign-jurisdiction inference cluster she has no contract with. David does not know either. There is no log, no receipt, no deletion path.

This is not a failure of any one person. It is a *structural* failure: the trust boundary between David's data and the remote LLM was never enforced. Deletion requests, opt-outs, and audit logs all happen **after** the wire.

The fix has to be earlier — on hardware David controls, **before** the wire. That's CloakBot.

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

CloakBot's intended upstream contract: detected sensitive spans become typed placeholders before the remote LLM sees the request. Math snippets are computed locally on raw values — the remote LLM only assembles the formula. Image uploads are OCR'd, sanitised, and redacted in-place with placeholder text overlaid on each black bar. Long document uploads are chunked, sanitised per chunk, then re-assembled with cross-chunk vault coalescing — same `<<PERSON_1>>` across chunks. None of this requires the remote model's cooperation — the boundary is enforced unilaterally.

---

## §3 Why Gemma 4 sits at the sweet spot

CloakBot needs a local model small enough for a single consumer GPU, capable of span-level entity extraction in structured JSON, multimodal in the same weights, and commercially redistributable. Gemma 4 E2B at 2B parameters sits at the sweet spot — ~5 GB, parseable JSON at temperature 0, native vision, Gemma license.

**vLLM for fast reproducible evals; Ollama for real-world adoption.** Why Ollama specifically: `ollama pull gemma:e2b` ships the model + OpenAI-compatible endpoint in one tool — no GGUF wrangling, no per-OS Metal/CUDA forks. With Ollama, CloakBot becomes a one-machine privacy appliance: start `gemma:e2b`, point the proxy at localhost, and every remote LLM request flows through the same local kernel. **Gemma 4 is the trust layer; Ollama is the deployment layer.**

---

## §4 Trust by measurement — three layers

Our harness answers one question per run: **did any ground-truth identifying token reach the upstream payload?** No comparable open eval exists for end-to-end pre-wire PII redaction across multi-turn LLMs — partly why we built this.

GPT paraphrases templates into 5 variants; Faker realises slots from fixed seeds (the ground truth); leak detection is literal substring matching. **GPT is not in the grading loop.** *Pair leak* = any identifying token leaked; *token leak* = fraction that escaped.

**A1 — text input, 4 domains × 20 sessions × 902 entity-turn pairs:**

| Domain | Pair leak | Token leak | Alias | p95 (ms) |
|---|---:|---:|---:|---:|
| Medical | **2.22%** | 2.44% | **95.00%** | 6,224 |
| Finance | 7.19% | 5.64% | **100.00%** | 5,937 |
| HR | 9.82% | 8.41% | n/a | 900 |
| Customer service | 12.90% | 6.15% | n/a | 5,822 |
| **Cross-domain** | **7.98%** | **5.88%** | **97.14%** | 6,224 |

Per-type detail: 100% on EMAIL/PHONE/FINANCE/IP/URL · 96.88% PERSON · **95% MEDICAL** (from a 20% baseline). **Medical buys accuracy with latency** — entity density triggers detector concurrency (see §7).

**A2 — visual, 10 invoice seeds × 180 PII spans:** **span leak 1.11%, token leak 1.01%** after redact + re-OCR (placeholder text rendered *inside* each black bar). 8 of 10 label categories ship at 0% leak.

**A3 — long-document chunker path, 3 domains × 20 sessions × 1,790 pairs:** **pair leak 6.26%, token leak 6.63%**, **cross-path alias 93.86%** (the `<<PERSON_1>>` from chunking carries to David's short follow-up turn). **0 of 226 seam leaks fall within the 300-char overlap band** — the chunker boundary heuristic has perfect coverage; every long-doc leak is an intra-chunk detector miss, never a seam dropout. Best template (`long_email_v1`, 7,000-char memos) lands at **1.15% token leak, 100% cross-path alias**.

---

## §5 The eval evaluates the eval

The harness has caught two of its own bugs — both silently inflated recall and had to be fixed before any detector iteration mattered:

- v1 scored leaks by full-value substring match. `Garcia Light, West Melanieview, AS` looked like 100% recall because two ZIP digits were masked, even though the alphabetic body was naked. We switched to token-level scoring.
- v2 counted "this entity appears in turn N" by any-identifying-token overlap, so surname collisions (`Johnson` in both a person and a company) faked multi-turn recurrence. We tightened appearance to full-value while keeping leak detection at token level.

All three detector iterations were *type-driven*, not *rule-driven*. v1 added four prompt rules (*"medications with dosages → MEDICAL"*); MEDICAL recall stayed at 20%. v2 deleted the rules and put the same info into `EntitySpec(medical).examples` as concrete strings (`metformin 500mg`, `hypertension diagnosed 2023`); recall jumped to 95%. **Small models lean on examples better than rule lists.** The v2 ORG/ID rebalance later lifted cross-domain alias 93.94% → 97.14% while shaving ~150 prompt tokens.

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

| Agent (code name) | What it solves at scale |
|---|---|
| `PrivacyRuntime` | One coordinated turn — input sanitise, intent route, restore, audit |
| `PiiDetector` (general + digit + intent fan-out) | Hot path under p95 1s for non-medical density |
| `ToolPrivacyInterceptor` | Tool I/O restoration; severity-gated approval; `read_file` / web_fetch / MCP inside a bank |
| `Session Vault` | Audit-traceable placeholder ↔ raw mapping, per-session, on disk |
| `ToolPrivacyDetector` + chunkers (*DocChunker* in diagram) | The path a 50-page contract takes through the kernel |
| `VisualPrivacyPipeline` | The path an X-ray, an invoice, a screenshot takes |

Compliance falls out naturally: the per-session vault is **GDPR Article 17's** deletion path; **HIPAA-aligned** because raw PHI never crosses the local boundary. CloakBot demos this at consumer scale on David's laptop. **It is the same architecture a bank, a clinic, or a law firm needs.**

---

## §7 What's left honest

- **ORG short / hyphenated names**: 71.67% pair recall — the largest A1 gap.
- **Weekday-form dates** (*"Friday at 3:21 PM"*): 84% pair recall — Gemma 4 treats weekday as generic.
- **`stage 2 chronic kidney disease`** and similar long medical phrases slip occasionally.
- Three A2 residual leaks across 10 invoices — `Turner Ltd` (2-token org) plus character-level OCR noise on two single-token emails.
- **Latency**: Medical p95 6.2s reflects detector concurrency on entity-dense turns; HR p95 0.9s is the typical hot path. Streaming + per-turn batching is the next milestone.
- Sub-3% PERSON / DATE variance isn't reproducible at the same prompt — Gemma 4 E2B isn't bit-deterministic at T=0; we treat that band as intrinsic noise.

---

## §8 Reproducibility

Public repo: [`github.com/spire-studio/cloakbot`](https://github.com/spire-studio/cloakbot). One command per layer reproduces every number:

```bash
# A1 — text input  (4 domains × 20 sessions, ~3 min/template)
for t in medical_followup_v1 hr_candidate_intake_v1 \
         finance_invoice_dispute_v1 customer_service_account_lockout_v1; do
  uv run python -m tests.eval.runners.text_leak_eval \
    --template tests/eval/templates/${t}.yaml \
    --paraphrased tests/eval/corpus/generated/${t}.paraphrased.yaml \
    --seeds 42 137 256 1024 --quiet
done && uv run python -m tests.eval.runners.rollup

# A2 — visual  (no vLLM needed; Faker + PIL + Tesseract)
uv run python -m tests.eval.runners.visual_leak_eval --seeds 0..9

# A3 — long-document  (3 templates × 5 variants × 4 seeds)
for t in long_email_v1 long_legal_correspondence_v1 long_tech_ticket_v1; do
  uv run python -m tests.eval.runners.long_doc_leak_eval \
    --template tests/eval/templates/long/${t}.yaml \
    --paraphrased tests/eval/corpus/generated/${t}.paraphrased.yaml \
    --seeds 42 137 256 1024 --quiet
done && uv run python -m tests.eval.runners.long_doc_rollup
```

Audit log: `tests/eval/reports/gpt_audit.jsonl`. A/B snapshots: `tests/eval/reports/2026-05-1{4,5}/`.

---

## §9 Why this matters now

*"Don't be evil"* was a motto.

In 2026, ***can't see evil* has to be an architecture.** For David's clients, the data that crosses the wire is non-revocable. The only durable fix is to move enforcement **before the wire**: local, auditable, measurable, and independent of the remote model's cooperation.

We built that kernel on Gemma 4 E2B, fit it on David's MacBook Air through Ollama, and backed it with 2,872 entity-test instances of receipts. We shipped it open-source — so the architecture David runs tonight is the same architectural pattern a Fortune 500 can harden, audit, and deploy.

This is what privacy-by-construction looks like in 2026.

---

*— Built by [Laurie Luo](mailto:me@laurie.pro) for the Gemma 4 Good Hackathon, May 2026.*
