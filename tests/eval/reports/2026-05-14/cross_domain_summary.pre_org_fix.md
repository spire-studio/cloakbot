# Cross-domain text leak summary — 2026-05-14

Pipeline: ``PrivacyRuntime.prepare_turn`` on Gemma 4 E2B via vLLM.
Aggregating 4 domain template(s).

## Cross-domain headline

| Metric | Value |
|---|---:|
| Domains | 4 |
| Total sessions | 80 |
| Total entity-turn pairs | 902 |
| Pair leaks | 80 |
| **Cross-domain pair leak** | **8.87%** |
| Identifying tokens | 1972 |
| Token leaks | 126 |
| **Cross-domain token leak** | **6.39%** |
| Multi-turn recurring entities | 33 |
| **Cross-domain alias consistency** | **93.94%** |
| p95 turn latency (worst across domains) | 6205 ms |

## Per domain

| Domain | Template | Sessions | Pairs | Pair leak | Token leak | Alias | p95 (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| `customer_service` | `customer_service_account_lockout_v1` | 20 | 155 | 10.97% | 5.23% | n/a | 5738 |
| `finance` | `finance_invoice_dispute_v1` | 20 | 292 | 9.59% | 7.05% | 92.31% | 1039 |
| `hr` | `hr_candidate_intake_v1` | 20 | 275 | 9.45% | 7.30% | n/a | 886 |
| `medical` | `medical_followup_v1` | 20 | 180 | 5.00% | 5.11% | 95.00% | 6205 |

## Per-entity-type recall (cross-domain)

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 93.75% | 98.43% | 80 | 5 | 445 | 7 |
| `DATE` | 85.71% | 89.80% | 140 | 20 | 245 | 25 |
| `EMAIL` | 100.00% | 100.00% | 60 | 0 | 110 | 0 |
| `FINANCE` | 100.00% | 100.00% | 72 | 0 | 112 | 0 |
| `ID` | 86.11% | 89.23% | 180 | 25 | 260 | 28 |
| `IP` | 100.00% | 100.00% | 15 | 0 | 35 | 0 |
| `MEDICAL` | 85.00% | 83.81% | 40 | 6 | 105 | 17 |
| `ORG` | 68.33% | 68.80% | 60 | 19 | 125 | 39 |
| `PERSON` | 96.88% | 96.88% | 160 | 5 | 320 | 10 |
| `PHONE` | 100.00% | 100.00% | 80 | 0 | 200 | 0 |
| `URL` | 100.00% | 100.00% | 15 | 0 | 15 | 0 |
