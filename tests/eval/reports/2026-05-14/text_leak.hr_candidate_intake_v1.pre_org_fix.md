# Text leak eval — 2026-05-14

- **Template:** `hr_candidate_intake_v1`
- **Variants:** 5 (paraphrased; slots preserved)
- **Seeds per variant:** 4
- **Total sessions:** 20
- **Detector:** google/gemma-4-e2b-it via vLLM @ http://8.131.77.138:8001/v1

Leaks are measured at two granularities. A **pair** is one (entity, user turn). A pair leaks if ANY identifying token from the entity reaches prepared text. **Token leak rate** is the fraction of identifying tokens that escaped — sharper when a multi-token entity (like a full address) is only partially masked.

## Aggregate

| Metric | Value |
|---|---:|
| Entity-turn pairs | 275 |
| Leaked pairs | 26 |
| **Pair leak rate** | **9.45%** |
| Identifying tokens | 630 |
| Leaked tokens | 46 |
| **Token leak rate** | **7.30%** |
| Alias consistency across turns | n/a |
| Multi-turn recurring entities | 0 |
| p50 turn latency | 643 ms |
| p95 turn latency | 886 ms |
| p99 turn latency | 1012 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 85.00% | 97.60% | 20 | 3 | 125 | 3 |
| `DATE` | 87.50% | 87.50% | 40 | 5 | 80 | 10 |
| `EMAIL` | 100.00% | 100.00% | 20 | 0 | 40 | 0 |
| `FINANCE` | 100.00% | 100.00% | 40 | 0 | 80 | 0 |
| `ID` | 75.00% | 75.00% | 20 | 5 | 20 | 5 |
| `ORG` | 77.50% | 77.78% | 40 | 9 | 90 | 20 |
| `PERSON` | 93.33% | 93.33% | 60 | 4 | 120 | 8 |
| `PHONE` | 100.00% | 100.00% | 20 | 0 | 60 | 0 |
| `URL` | 100.00% | 100.00% | 15 | 0 | 15 | 0 |

## First leaks (truncated to 15)

| Session | Turn | Type | Slot | Value | Leaked tokens |
|---|---:|---|---|---|---|
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:42` | 6 | `ID` | `ssn_last4` | `1316` | `1316` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:137` | 4 | `ORG` | `prev_employer` | `Taylor-Simmons` | `Taylor`, `Simmons` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:137` | 2 | `DATE` | `start_date` | `December 2023` | `December`, `2023` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:256` | 4 | `ORG` | `prev_employer` | `Guzman-Morrow` | `Guzman`, `Morrow` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:256` | 2 | `DATE` | `start_date` | `July 2022` | `July`, `2022` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:1024` | 2 | `DATE` | `start_date` | `March 2026` | `March`, `2026` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:1024` | 6 | `ID` | `ssn_last4` | `3255` | `3255` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:42` | 2 | `ORG` | `current_employer` | `Miller, Henderson and Johnson` | `Miller`, `Henderson`, `Johnson` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:42` | 4 | `ORG` | `prev_employer` | `Hall PLC` | `Hall` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:42` | 2 | `DATE` | `start_date` | `March 2024` | `March`, `2024` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:137` | 2 | `ORG` | `current_employer` | `Morris, Sanders and Rivas` | `Morris`, `Sanders`, `Rivas` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:137` | 4 | `PERSON` | `reference_colleague` | `April Johnson` | `April`, `Johnson` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:256` | 2 | `ORG` | `current_employer` | `Contreras-Hawkins` | `Contreras`, `Hawkins` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:256` | 2 | `DATE` | `start_date` | `July 2022` | `July`, `2022` |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:1024` | 2 | `ORG` | `current_employer` | `Diaz, Morton and Roman` | `Diaz`, `Morton`, `Roman` |

## Per-session leak summary

| Session | Pairs | Pair leaks | Pair rate | Token leak rate | Alias |
|---|---:|---:|---:|---:|---:|
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:42` | 13 | 1 | 7.69% | 3.45% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:137` | 14 | 2 | 14.29% | 12.12% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:256` | 14 | 2 | 14.29% | 12.12% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p00:1024` | 14 | 2 | 14.29% | 9.68% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:42` | 13 | 3 | 23.08% | 20.69% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:137` | 14 | 2 | 14.29% | 15.15% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:256` | 14 | 2 | 14.29% | 12.12% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p01:1024` | 14 | 2 | 14.29% | 16.13% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p02:42` | 13 | 0 | 0.00% | 0.00% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p02:137` | 14 | 1 | 7.14% | 6.06% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p02:256` | 14 | 1 | 7.14% | 3.03% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p02:1024` | 14 | 0 | 0.00% | 0.00% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p03:42` | 13 | 0 | 0.00% | 0.00% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p03:137` | 14 | 2 | 14.29% | 9.09% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p03:256` | 14 | 2 | 14.29% | 9.09% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p03:1024` | 14 | 0 | 0.00% | 0.00% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p04:42` | 13 | 1 | 7.69% | 3.45% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p04:137` | 14 | 1 | 7.14% | 3.03% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p04:256` | 14 | 0 | 0.00% | 0.00% | n/a |
| `eval:hr_candidate_intake_v1:hr_candidate_intake_v1_p04:1024` | 14 | 2 | 14.29% | 9.68% | n/a |
