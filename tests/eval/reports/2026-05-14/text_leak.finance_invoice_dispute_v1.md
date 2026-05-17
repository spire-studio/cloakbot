# Text leak eval — 2026-05-14

- **Template:** `finance_invoice_dispute_v1`
- **Variants:** 5 (paraphrased; slots preserved)
- **Seeds per variant:** 4
- **Total sessions:** 20
- **Detector:** google/gemma-4-e2b-it via vLLM @ http://8.131.77.138:8001/v1

Leaks are measured at two granularities. A **pair** is one (entity, user turn). A pair leaks if ANY identifying token from the entity reaches prepared text. **Token leak rate** is the fraction of identifying tokens that escaped — sharper when a multi-token entity (like a full address) is only partially masked.

## Aggregate

| Metric | Value |
|---|---:|
| Entity-turn pairs | 292 |
| Leaked pairs | 21 |
| **Pair leak rate** | **7.19%** |
| Identifying tokens | 567 |
| Leaked tokens | 32 |
| **Token leak rate** | **5.64%** |
| Alias consistency across turns | 100.00% |
| Multi-turn recurring entities | 15 |
| p50 turn latency | 754 ms |
| p95 turn latency | 5937 ms |
| p99 turn latency | 6423 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 100.00% | 100.00% | 20 | 0 | 105 | 0 |
| `DATE` | 100.00% | 100.00% | 60 | 0 | 105 | 0 |
| `EMAIL` | 100.00% | 100.00% | 20 | 0 | 35 | 0 |
| `FINANCE` | 100.00% | 100.00% | 32 | 0 | 32 | 0 |
| `ID` | 90.00% | 93.75% | 100 | 10 | 160 | 10 |
| `ORG` | 45.00% | 37.14% | 20 | 11 | 35 | 22 |
| `PERSON` | 100.00% | 100.00% | 20 | 0 | 40 | 0 |
| `PHONE` | 100.00% | 100.00% | 20 | 0 | 55 | 0 |

## First leaks (truncated to 15)

| Session | Turn | Type | Slot | Value | Leaked tokens |
|---|---:|---|---|---|---|
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:256` | 0 | `ORG` | `vendor` | `Sanchez-Hunt` | `Sanchez`, `Hunt` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:256` | 4 | `ID` | `card_last4` | `2655` | `2655` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:256` | 6 | `ID` | `card_last4` | `2655` | `2655` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:1024` | 0 | `ORG` | `vendor` | `Garcia, Hunt and Frye` | `Garcia`, `Hunt`, `Frye` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:1024` | 4 | `ID` | `card_last4` | `0542` | `0542` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:1024` | 6 | `ID` | `card_last4` | `0542` | `0542` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:42` | 0 | `ORG` | `vendor` | `Taylor Inc` | `Taylor` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:42` | 4 | `ID` | `card_last4` | `6542` | `6542` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:42` | 6 | `ID` | `card_last4` | `6542` | `6542` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:137` | 0 | `ORG` | `vendor` | `Freeman Inc` | `Freeman` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:256` | 0 | `ORG` | `vendor` | `Sanchez-Hunt` | `Sanchez`, `Hunt` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:1024` | 4 | `ID` | `card_last4` | `0542` | `0542` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:1024` | 6 | `ID` | `card_last4` | `0542` | `0542` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p02:256` | 0 | `ORG` | `vendor` | `Sanchez-Hunt` | `Sanchez`, `Hunt` |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p03:256` | 0 | `ORG` | `vendor` | `Sanchez-Hunt` | `Sanchez`, `Hunt` |

## Per-session leak summary

| Session | Pairs | Pair leaks | Pair rate | Token leak rate | Alias |
|---|---:|---:|---:|---:|---:|
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:42` | 14 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:137` | 14 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:256` | 14 | 3 | 21.43% | 15.38% | n/a |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p00:1024` | 14 | 3 | 21.43% | 16.13% | n/a |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:42` | 15 | 3 | 20.00% | 11.11% | n/a |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:137` | 15 | 1 | 6.67% | 3.45% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:256` | 15 | 1 | 6.67% | 7.41% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p01:1024` | 14 | 2 | 14.29% | 6.45% | n/a |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p02:42` | 15 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p02:137` | 15 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p02:256` | 15 | 1 | 6.67% | 7.41% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p02:1024` | 14 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p03:42` | 15 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p03:137` | 15 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p03:256` | 15 | 1 | 6.67% | 7.41% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p03:1024` | 14 | 1 | 7.14% | 9.68% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p04:42` | 15 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p04:137` | 15 | 1 | 6.67% | 3.45% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p04:256` | 15 | 1 | 6.67% | 7.41% | 100.00% |
| `eval:finance_invoice_dispute_v1:finance_invoice_dispute_v1_p04:1024` | 14 | 3 | 21.43% | 16.13% | n/a |
