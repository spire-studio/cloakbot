# Text leak eval — 2026-05-14

- **Template:** `medical_followup_v1`
- **Variants:** 5 (paraphrased; slots preserved)
- **Seeds per variant:** 1
- **Total sessions:** 5
- **Detector:** google/gemma-4-e2b-it via vLLM @ http://8.131.77.138:8001/v1

Leaks are measured at two granularities. A **pair** is one (entity, user turn). A pair leaks if ANY identifying token from the entity reaches prepared text. **Token leak rate** is the fraction of identifying tokens that escaped — sharper when a multi-token entity (like a full address) is only partially masked.

## Aggregate

| Metric | Value |
|---|---:|
| Entity-turn pairs | 45 |
| Leaked pairs | 3 |
| **Pair leak rate** | **6.67%** |
| Identifying tokens | 105 |
| Leaked tokens | 4 |
| **Token leak rate** | **3.81%** |
| Alias consistency across turns | 100.00% |
| Multi-turn recurring entities | 5 |
| p50 turn latency | 799 ms |
| p95 turn latency | 6141 ms |
| p99 turn latency | 6321 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 100.00% | 100.00% | 5 | 0 | 30 | 0 |
| `DATE` | 100.00% | 100.00% | 5 | 0 | 10 | 0 |
| `ID` | 100.00% | 100.00% | 5 | 0 | 10 | 0 |
| `MEDICAL` | 70.00% | 73.33% | 10 | 3 | 15 | 4 |
| `PERSON` | 100.00% | 100.00% | 15 | 0 | 30 | 0 |
| `PHONE` | 100.00% | 100.00% | 5 | 0 | 10 | 0 |

## First leaks (truncated to 15)

| Session | Turn | Type | Slot | Value | Leaked tokens |
|---|---:|---|---|---|---|
| `eval:medical_followup_v1:medical_followup_v1_p02:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` | `hypertension` |
| `eval:medical_followup_v1:medical_followup_v1_p02:42` | 0 | `MEDICAL` | `medication` | `Atorvastatin 40mg nightly` | `Atorvastatin`, `nightly` |
| `eval:medical_followup_v1:medical_followup_v1_p03:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` | `hypertension` |

## Per-session leak summary

| Session | Pairs | Pair leaks | Pair rate | Token leak rate | Alias |
|---|---:|---:|---:|---:|---:|
| `eval:medical_followup_v1:medical_followup_v1_p00:42` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p01:42` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p02:42` | 9 | 2 | 22.22% | 14.29% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p03:42` | 9 | 1 | 11.11% | 4.76% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p04:42` | 9 | 0 | 0.00% | 0.00% | 100.00% |
