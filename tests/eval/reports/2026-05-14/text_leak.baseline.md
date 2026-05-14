# Text leak eval — 2026-05-14

- **Template:** `medical_followup_v1`
- **Variants:** 5 (paraphrased; slots preserved)
- **Seeds per variant:** 1
- **Total sessions:** 5
- **Detector:** google/gemma-4-e2b-it via vLLM @ http://8.131.77.138:8001/v1

## Aggregate

| Metric | Value |
|---|---:|
| Entity-turn pairs | 45 |
| Leaked pairs | 8 |
| **Leak rate** | **17.78%** |
| Alias consistency across turns | 100.00% |
| Multi-turn recurring entities | 5 |
| p50 turn latency | 647 ms |
| p95 turn latency | 6176 ms |
| p99 turn latency | 6596 ms |

## Per-entity-type recall

| Type | Recall | Occurrences | Leaks |
|---|---:|---:|---:|
| `ADDRESS` | 100.00% | 5 | 0 |
| `DATE` | 100.00% | 5 | 0 |
| `ID` | 100.00% | 5 | 0 |
| `MEDICAL` | 20.00% | 10 | 8 |
| `PERSON` | 100.00% | 15 | 0 |
| `PHONE` | 100.00% | 5 | 0 |

## First leaks (truncated to 10)

| Session | Turn | Type | Slot | Value |
|---|---:|---|---|---|
| `eval:medical_followup_v1:medical_followup_v1_p00:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` |
| `eval:medical_followup_v1:medical_followup_v1_p00:42` | 0 | `MEDICAL` | `medication` | `Atorvastatin 40mg nightly` |
| `eval:medical_followup_v1:medical_followup_v1_p01:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` |
| `eval:medical_followup_v1:medical_followup_v1_p01:42` | 0 | `MEDICAL` | `medication` | `Atorvastatin 40mg nightly` |
| `eval:medical_followup_v1:medical_followup_v1_p02:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` |
| `eval:medical_followup_v1:medical_followup_v1_p03:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` |
| `eval:medical_followup_v1:medical_followup_v1_p03:42` | 0 | `MEDICAL` | `medication` | `Atorvastatin 40mg nightly` |
| `eval:medical_followup_v1:medical_followup_v1_p04:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` |

## Per-session leak summary

| Session | Pairs | Leaks | Leak rate | Alias consistency |
|---|---:|---:|---:|---:|
| `eval:medical_followup_v1:medical_followup_v1_p00:42` | 9 | 2 | 22.22% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p01:42` | 9 | 2 | 22.22% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p02:42` | 9 | 1 | 11.11% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p03:42` | 9 | 2 | 22.22% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p04:42` | 9 | 1 | 11.11% | 100.00% |
