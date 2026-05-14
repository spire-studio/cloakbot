# CloakBot — Privacy by Construction with Gemma 4

**Draft writeup for [The Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon), Safety & Trust track.**
*Target length ≈ 1800 words. Sections marked* `TODO` *need your touch before submission.*

---

## TL;DR

CloakBot is a **local privacy proxy** that lets people use any frontier remote LLM (Claude, GPT, Gemini) without their personal data ever leaving the device. The trust kernel is **Gemma 4 E2B running locally through vLLM** — three specialised detectors, one intent classifier, one multimodal pass for images and PDFs, all coordinated by a Python pipeline that swaps PII for typed placeholders before any byte crosses the network boundary.

We didn't trust ourselves to *say* CloakBot keeps its promise — we **built an end-to-end leak evaluation harness** across **4 domains** (medical · HR · finance · customer service), **80 multi-turn sessions**, **902 entity-turn pairs**, **11 PII types**. The harness drove three rounds of prompt redesign and exposed two measurement bugs in our own eval code along the way.

Current cross-domain baseline:

- **Pair leak rate: 7.98%** (medical alone: 2.22%, down 87.5% from the pre-eval baseline of 17.78%)
- **Token leak rate: 5.88%**
- **Alias consistency across turns: 97.14%** (in the two domains with naturally-recurring entities — medical 95%, finance 100%)
- **100% recall** on EMAIL · PHONE · FINANCE · IP · URL
- p50 turn latency 0.7 s, p95 0.9 – 6.2 s depending on domain

The full harness reproduces from one command in the repo.

---

## The problem (≈ 200 words) `TODO: tighten with personal anecdote`

Every conversation a person has with a remote LLM today is a privacy transaction with no receipt:

- A rural family doctor asking ChatGPT to summarise a patient's symptoms ships the patient's name, diagnosis, and medication list to a vendor that has no clinical relationship with the patient.
- An HR clerk pasting a candidate's CV into Claude for a "fit summary" exports the candidate's full contact information, SSN-shaped IDs, and salary expectations into a foreign-jurisdiction inference cluster.
- A college student asking Gemini to proofread a personal essay leaks the essay's named relatives, addresses, mental-health context.

Existing fixes don't fix this. Deletion is post-hoc. Opt-outs leak by default. Self-hosted models can't yet match frontier capability for most user tasks. The actual fix is **structural**: a privacy boundary that's enforced **before** the trust line, on hardware the user controls.

That's CloakBot.

---

## What CloakBot does (≈ 250 words)

```
User message + attachments
  ─► [local] PrivacyRuntime
      • GeneralPrivacyDetector  (Gemma 4 — PII other than numbers)
      • DigitPrivacyDetector    (Gemma 4 — money, dates, IDs, vitals)
      • IntentAnalyzer          (Gemma 4 — chat vs. math)
      • VisualPrivacyPipeline   (Gemma 4 multimodal + OCR + bbox)
      • ToolPrivacyDetector     (Gemma 4 — long tool outputs, chunked)
      • Session Vault           (placeholder ↔ raw mapping, on disk, per-session)
  ─► [over network] Remote LLM sees ONLY placeholder text:
      "What is 18% of <<FINANCE_1>>?"   not   "What is 18% of $142,500?"
  ─► [local] Restore + math execute
      • <python_snippet_N> blocks executed locally with raw values from the vault
      • <<PERSON_1>> swapped back to "Alice" for the user-visible reply
      • Per-turn transparency report attached
```

Every byte the remote model sees is a typed placeholder. Math snippets are computed locally on raw values — the remote LLM only assembles the formula. Image attachments get OCR'd, sanitised, and redacted in-place with placeholder text overlaid on each redaction box, so the remote model can still refer to the redacted region by name without ever seeing it. None of this requires the remote model's cooperation — the boundary is enforced unilaterally by the local kernel.

---

## Why Gemma 4 is the kernel (≈ 200 words)

CloakBot needs a local model that is:

1. **Small enough to run on a single consumer GPU.** Gemma 4 E2B at 2B parameters fits in ~5 GB.
2. **Capable enough to do span-level entity extraction in structured JSON.** Gemma 4 is one of the few open models that reliably emits parseable JSON under temperature 0.
3. **Multimodal.** The visual pipeline needs vision + OCR-aligned reasoning. Gemma 4 handles both.
4. **Licensed for downstream commercial use** so projects like CloakBot can be redistributed.

We run Gemma 4 through vLLM's OpenAI-compatible endpoint. The detector orchestrator fans out concurrent calls (general + digit + intent + visual + tool-output), then merges by exact substring overlap. Cross-domain we see **p50 ≈ 0.7 s, p95 between 0.9 s and 6.2 s** depending on density and per-turn detector cold-start (see Evaluation below).

The remote LLM is interchangeable. We tested Claude, GPT, and Gemini against the same sanitised stream — none of them require any client-side change.

---

## Evaluation (≈ 700 words — the heart of this submission)

We refused to ship trust-by-assertion. We built an end-to-end leak evaluation harness under `tests/eval/` that runs on the actual production pipeline and answers one question per run: **did any ground-truth identifying token reach the upstream payload?**

### How it works

```
templates/medical_followup_v1.yaml          ← hand-authored multi-turn dialogue
                                              with {slot} tokens
                                                ↓
generators/paraphrase_with_gpt.py           ← GPT (gpt-5.4) paraphrases each
                                              template into 5 prose variants
                                              while preserving slot tokens
                                                ↓
generators/faker_filler.py                  ← Faker realises each slot with a
                                              fixed seed → reproducible
                                              ground truth values
                                                ↓
runners/text_leak_eval.py                   ← drives each session through
                                              PrivacyRuntime.prepare_turn,
                                              measures leak at TWO granularities
                                                ↓
reports/<date>/text_leak.md, .jsonl         ← per-session + aggregate
```

The key design choice: **GPT is not in the grading loop**. Faker emits the ground-truth values, leak detection is literal substring matching, results are deterministic.

### Two leak granularities

- **Pair leak rate**: an (entity, user-turn) pair leaks if **any** identifying token from the entity reaches prepared text. This is the headline number — even a partial leak is a leak.
- **Token leak rate**: the fraction of identifying tokens that escape. Sharper when a multi-token entity (like a full address) is only partially masked. *"Identifying" = digits of length ≥ 3 (postal codes, IDs) or alphanumeric tokens of length ≥ 4 (names, cities, drug names).*

**The eval has caught two of its own bugs so far** — both of them silently inflated recall and had to be fixed before any detector iteration was meaningful:

- v1 scored leaks by full-value substring match, which made `ADDRESS` look 100% recall when in reality `Garcia Light, West Melanieview, AS` was leaking around two masked digits. We switched to token-level scoring.
- v2 counted "this entity appears in turn N" by *any-identifying-token overlap* with the turn's raw text, which made surname collisions (e.g. "Johnson" appearing in both a person name and a company name) look like multi-turn recurrence. We tightened the appearance check to full-value substring while keeping leak detection at token level. **The eval evaluates the eval.**

### Multi-turn metric

`alias_consistency_across_turns` is the metric we care about most. For each ground-truth value that appears verbatim in ≥ 2 user turns, we look up which placeholder is protecting it (via token-overlap against the session vault) and check that the same placeholder appears in every relevant turn's prepared text. In templates where the conversation does not naturally repeat a PII value (HR and customer service in our suite), there are no multi-turn entities to score, and the metric reports `n/a` for those domains rather than fake recurrence into existence.

### Cross-domain headline (current, post-iteration v2)

| Domain | Sessions | Pairs | Pair leak | Token leak | Alias | p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Medical (`medical_followup_v1`) | 20 | 180 | **2.22%** | 2.44% | **95.00%** | 6224 |
| HR (`hr_candidate_intake_v1`) | 20 | 275 | 9.82% | 8.41% | n/a* | 900 |
| Finance (`finance_invoice_dispute_v1`) | 20 | 292 | 7.19% | 5.64% | **100.00%** | 5937 |
| Customer service (`customer_service_account_lockout_v1`) | 20 | 155 | 12.90% | 6.15% | n/a* | 5822 |
| **All domains** | **80** | **902** | **7.98%** | **5.88%** | **97.14%** | 6224 |

*\* HR and customer service templates have no entity values that naturally recur across user turns; the alias metric does not apply.*

### Per-entity-type recall across all 80 sessions

| Type | Pair recall | Token recall | Pairs | Pair leaks | Notes |
|---|---:|---:|---:|---:|---|
| `EMAIL` | **100%** | **100%** | 60 | 0 | |
| `FINANCE` | **100%** | **100%** | 72 | 0 | currency-anchored numerics caught reliably |
| `IP` | **100%** | **100%** | 15 | 0 | |
| `PHONE` | **100%** | **100%** | 80 | 0 | |
| `URL` | **100%** | **100%** | 15 | 0 | |
| `PERSON` | 96.88% | 96.88% | 160 | 5 | small-model variance on rare names |
| `MEDICAL` | **95.00%** | 92.38% | 40 | 2 | up from 20% baseline through type-driven examples |
| `ADDRESS` | 90.00% | 96.18% | 80 | 8 | most "leaks" are 1 token of a long span |
| `ID` | 90.00% | 93.08% | 180 | 18 | username-form IDs were a regression / recovery (see v2) |
| `DATE` | 84.29% | 88.98% | 140 | 22 | weekday-based dates ("Friday at 3:21 PM") slip |
| **`ORG`** | **71.67%** | **71.20%** | 60 | 17 | **weakest remaining type** — short / hyphenated company names |

### What the eval *taught* us

1. **Gemma 4 E2B was blind to single-word common diagnoses.** `hypertension`, `atrial fibrillation`, `asthma` were treated as generic clinical concepts, not as personally-bound PII. Five of five paraphrase variants leaked these consistently.
2. **The numeric detector was hijacking address numbers.** Street numbers and ZIP codes (`65423`, `06196`) were being extracted as standalone `VALUE` entities, leaving the alphabetic middle of the address (`Garcia Light, West Melanieview, AS`) exposed in prepared text.
3. **Long rule lists hurt small-model recall.** Our first fix added four verbose rules to the general detector's prompt. MEDICAL recall *dropped* on the same sample because Gemma 4 E2B couldn't chain through the override semantics fast enough — we deleted the rules and moved the same information into the type registry's `examples` field instead.
4. **Examples crowd attention across types — they don't just help the type they describe.** When we added 10 ORG examples in v1, CS ID recall regressed from 95% to 65% (lowercased username strings like `donaldgarcia` started being missed) — the new ORG-shaped examples competed for the model's attention budget. We trimmed ORG to 7 examples and added 6 ID examples in v2; CS ID recovered to 90%, HR ORG held at ~85%, and cross-domain alias jumped from 94% to 97%.

### What we fixed (three iterations)

All three detector iterations were *type-driven*, not *rule-driven*:

| iteration | change | headline result |
|---|---|---|
| v0 → v1 | `EntitySpec` got an `examples: List[str]` field; populated `medical` and `address` examples; collapsed 4 prompt rules into 1 | MEDICAL recall 20% → 85%, ADDRESS recovered from a measurement artifact |
| v1 → v2 (org) | Added 10 ORG examples covering `PLC` / `Corp` / hyphenated / comma-separated shapes | HR ORG 77.5% → 92.5%; **but** CS ID regressed 95% → 65% (over-fitting "name-like ORG" patterns blurred username detection) |
| v2 (org) → v2 (final) | Trimmed ORG examples to 7, added 6 explicit ID examples (`ACCT-…`, `INV-…`, `jsmith2024`, `john.doe`, `case ref #4731`) | CS ID 65% → 90%, cross-domain pair leak 8.87% → 7.98%, cross-domain alias 93.94% → 97.14% |

Net prompt length **decreased** by ~150 tokens vs. v0. MEDICAL recall went from 20% to **95%** over three iterations.

### Known issues we're keeping honest

- **ORG short / hyphenated / comma-separated company names** are the largest remaining gap (71.67% pair recall). Further coverage means adding more shapes to `EntitySpec(org).examples` — but each added example slightly increases the risk of crowding adjacent types (we saw this hurt CS ID in v1), so any future addition needs the eval to re-verify cross-domain.
- **CS `callback_time` weekday-based dates** ("Friday at 3:21 PM", "Saturday at 2:39 AM") reproducibly leak the weekday token (DATE 84.29% pair recall cross-domain, 20% in CS alone). Gemma 4 treats the weekday as a generic word rather than a private appointment cue. Fix path: add weekday-format examples to the `temporal` spec; left for a future iteration.
- **A military FPO address** (`USCGC Cowan, FPO AP 53420`) reproducibly leaks. Rare corner case; we chose not to over-fit `address` examples to it.
- **`stage 2 chronic kidney disease`** slips occasionally — long medical phrases still need more example coverage.
- A few PERSON / DATE leaks across runs are not reproducible at the same prompt — Gemma 4 E2B is not bit-deterministic even at temperature 0, and we treat sub-3% variance as the model's intrinsic noise rather than a prompt bug.

---

## Demo `TODO: 2-3 minute video`

- Show: medical case opening, image of an invoice with the visual pipeline running, multi-turn "what's my mom's copay" → math executed locally.
- Side-by-side toggle: "what you typed" vs "what the remote saw".
- The eval harness running live — `pair leak: 2.22% (medical) / 7.98% (cross-domain)` ticker in the corner.

---

## What's next (≈ 120 words)

- **Push ORG further** (71.67% pair recall — still the weakest type). Future example additions need the eval to re-verify cross-domain so we don't repeat the v1 attention-budget regression that bled into CS ID.
- **Weekday-based dates** (`Friday at 3:21 PM`) — add weekday-format examples to `EntitySpec(temporal)` and re-run CS to confirm DATE recall closes the gap.
- **Multi-turn coverage**: HR and customer service templates have no naturally-recurring entities, so `alias_consistency` reports `n/a` for those domains. Either add a recurrence-forcing turn (caller restating the candidate's name when handed off) or accept that those domains exercise density rather than recurrence.
- **A2 — visual eval**: programmatic invoice + chat-screenshot renderer with pixel-level bbox ground truth. Re-OCR the redacted image and look for residual identifying tokens. Same `tests/eval/runners` directory.
- **Ollama fallback**: already supported for users without GPU access — needs documentation and a quickstart.
- **Browser extension**: clipboard-level guard so CloakBot's coverage isn't limited to its own chat UI.

---

## Repo & reproducibility

- Public code: [github.com/spire-studio/cloakbot](https://github.com/spire-studio/cloakbot)
- Eval directory: [`tests/eval/`](tests/eval/). One command per template reproduces every number above against a running vLLM endpoint in ≈ 3 minutes each:

  ```bash
  for t in medical_followup_v1 hr_candidate_intake_v1 \
           finance_invoice_dispute_v1 customer_service_account_lockout_v1; do
    uv run python -m tests.eval.runners.text_leak_eval \
      --template tests/eval/templates/${t}.yaml \
      --paraphrased tests/eval/corpus/generated/${t}.paraphrased.yaml \
      --seeds 42 137 256 1024 --quiet
  done
  uv run python -m tests.eval.runners.rollup
  ```

- Audit log: every GPT paraphrase call is logged to `tests/eval/reports/gpt_audit.jsonl` (model, prompt token count, completion, rejected variants).
- Snapshots of every intermediate A/B run (baseline / post-refactor / post-examples) are kept under `tests/eval/reports/2026-05-14/` for reviewer inspection.

---

## Why this fits the Safety & Trust track

The track brief calls out *"communities where privacy is critical"*. CloakBot's premise is exactly that: in environments where the user cannot trust the remote model — adversarial jurisdictions, regulated industries, vulnerable populations — Gemma 4 running locally **is** the trust kernel. Without it, there is no CloakBot. The hackathon evaluation we built turns "trust me, it works" into "here are 902 entity-turn pairs across 4 domains, 7.98% pair leak, 97.14% alias consistency, here's the data, here's the command to reproduce it".

---

*— Built by [Laurie Luo](mailto:me@laurie.pro) for the Gemma 4 Good Hackathon, May 2026.*
