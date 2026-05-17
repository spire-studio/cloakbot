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
| Token leaks | 113 |
| **Cross-domain token leak** | **5.73%** |
| Multi-turn recurring entities | 34 |
| **Cross-domain alias consistency** | **94.12%** |
| p95 turn latency (worst across domains) | 6423 ms |

## Per domain

| Domain | Template | Sessions | Pairs | Pair leak | Token leak | Alias | p95 (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| `customer_service` | `customer_service_account_lockout_v1` | 20 | 155 | 19.35% | 9.23% | n/a | 5796 |
| `finance` | `finance_invoice_dispute_v1` | 20 | 292 | 7.88% | 6.00% | 92.86% | 6423 |
| `hr` | `hr_candidate_intake_v1` | 20 | 275 | 7.64% | 5.40% | n/a | 910 |
| `medical` | `medical_followup_v1` | 20 | 180 | 3.33% | 3.33% | 95.00% | 6264 |

## Per-entity-type recall (cross-domain)

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 92.50% | 98.20% | 80 | 6 | 445 | 8 |
| `DATE` | 85.00% | 89.39% | 140 | 21 | 245 | 26 |
| `EMAIL` | 100.00% | 100.00% | 60 | 0 | 110 | 0 |
| `FINANCE` | 100.00% | 100.00% | 72 | 0 | 112 | 0 |
| `ID` | 81.67% | 86.92% | 180 | 33 | 260 | 34 |
| `IP` | 100.00% | 100.00% | 15 | 0 | 35 | 0 |
| `MEDICAL` | 92.50% | 91.43% | 40 | 3 | 105 | 9 |
| `ORG` | 80.00% | 79.20% | 60 | 12 | 125 | 26 |
| `PERSON` | 96.88% | 96.88% | 160 | 5 | 320 | 10 |
| `PHONE` | 100.00% | 100.00% | 80 | 0 | 200 | 0 |
| `URL` | 100.00% | 100.00% | 15 | 0 | 15 | 0 |
