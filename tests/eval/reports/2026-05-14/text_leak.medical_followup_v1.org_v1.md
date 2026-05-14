# Text leak eval — 2026-05-14

- **Template:** `medical_followup_v1`
- **Variants:** 5 (paraphrased; slots preserved)
- **Seeds per variant:** 4
- **Total sessions:** 20
- **Detector:** google/gemma-4-e2b-it via vLLM @ http://8.131.77.138:8001/v1

Leaks are measured at two granularities. A **pair** is one (entity, user turn). A pair leaks if ANY identifying token from the entity reaches prepared text. **Token leak rate** is the fraction of identifying tokens that escaped — sharper when a multi-token entity (like a full address) is only partially masked.

## Aggregate

| Metric | Value |
|---|---:|
| Entity-turn pairs | 180 |
| Leaked pairs | 6 |
| **Pair leak rate** | **3.33%** |
| Identifying tokens | 450 |
| Leaked tokens | 15 |
| **Token leak rate** | **3.33%** |
| Alias consistency across turns | 95.00% |
| Multi-turn recurring entities | 20 |
| p50 turn latency | 796 ms |
| p95 turn latency | 6264 ms |
| p99 turn latency | 6389 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 90.00% | 95.79% | 20 | 2 | 95 | 4 |
| `DATE` | 100.00% | 100.00% | 20 | 0 | 40 | 0 |
| `ID` | 100.00% | 100.00% | 20 | 0 | 40 | 0 |
| `MEDICAL` | 92.50% | 91.43% | 40 | 3 | 105 | 9 |
| `PERSON` | 98.33% | 98.33% | 60 | 1 | 120 | 2 |
| `PHONE` | 100.00% | 100.00% | 20 | 0 | 50 | 0 |

## First leaks (truncated to 15)

| Session | Turn | Type | Slot | Value | Leaked tokens |
|---|---:|---|---|---|---|
| `eval:medical_followup_v1:medical_followup_v1_p00:256` | 0 | `PERSON` | `doctor` | `Dana Hunt` | `Dana`, `Hunt` |
| `eval:medical_followup_v1:medical_followup_v1_p00:256` | 2 | `ADDRESS` | `address` | `USCGC Cowan, FPO AP 53420` | `USCGC`, `Cowan`, `53420` |
| `eval:medical_followup_v1:medical_followup_v1_p03:42` | 0 | `MEDICAL` | `diagnosis` | `hypertension` | `hypertension` |
| `eval:medical_followup_v1:medical_followup_v1_p03:137` | 0 | `MEDICAL` | `diagnosis` | `stage 2 chronic kidney disease` | `stage`, `chronic`, `kidney`, `disease` |
| `eval:medical_followup_v1:medical_followup_v1_p03:256` | 2 | `ADDRESS` | `address` | `USCGC Cowan, FPO AP 53420` | `53420` |
| `eval:medical_followup_v1:medical_followup_v1_p04:137` | 0 | `MEDICAL` | `diagnosis` | `stage 2 chronic kidney disease` | `stage`, `chronic`, `kidney`, `disease` |

## Per-session leak summary

| Session | Pairs | Pair leaks | Pair rate | Token leak rate | Alias |
|---|---:|---:|---:|---:|---:|
| `eval:medical_followup_v1:medical_followup_v1_p00:42` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p00:137` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p00:256` | 9 | 2 | 22.22% | 23.81% | 0.00% |
| `eval:medical_followup_v1:medical_followup_v1_p00:1024` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p01:42` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p01:137` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p01:256` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p01:1024` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p02:42` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p02:137` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p02:256` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p02:1024` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p03:42` | 9 | 1 | 11.11% | 4.76% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p03:137` | 9 | 1 | 11.11% | 16.67% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p03:256` | 9 | 1 | 11.11% | 4.76% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p03:1024` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p04:42` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p04:137` | 9 | 1 | 11.11% | 16.67% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p04:256` | 9 | 0 | 0.00% | 0.00% | 100.00% |
| `eval:medical_followup_v1:medical_followup_v1_p04:1024` | 9 | 0 | 0.00% | 0.00% | 100.00% |
