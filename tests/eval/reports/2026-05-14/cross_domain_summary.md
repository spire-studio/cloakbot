# Cross-domain text leak summary — 2026-05-14

Pipeline: ``PrivacyRuntime.prepare_turn`` on Gemma 4 E2B via vLLM.
Aggregating 4 domain template(s).

## Cross-domain headline

| Metric | Value |
|---|---:|
| Domains | 4 |
| Total sessions | 80 |
| Total entity-turn pairs | 902 |
| Pair leaks | 72 |
| **Cross-domain pair leak** | **7.98%** |
| Identifying tokens | 1972 |
| Token leaks | 116 |
| **Cross-domain token leak** | **5.88%** |
| Multi-turn recurring entities | 35 |
| **Cross-domain alias consistency** | **97.14%** |
| p95 turn latency (worst across domains) | 6224 ms |

## Per domain

| Domain | Template | Sessions | Pairs | Pair leak | Token leak | Alias | p95 (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| `customer_service` | `customer_service_account_lockout_v1` | 20 | 155 | 12.90% | 6.15% | n/a | 5822 |
| `finance` | `finance_invoice_dispute_v1` | 20 | 292 | 7.19% | 5.64% | 100.00% | 5937 |
| `hr` | `hr_candidate_intake_v1` | 20 | 275 | 9.82% | 8.41% | n/a | 900 |
| `medical` | `medical_followup_v1` | 20 | 180 | 2.22% | 2.44% | 95.00% | 6224 |

## Per-entity-type recall (cross-domain)

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 90.00% | 96.18% | 80 | 8 | 445 | 17 |
| `DATE` | 84.29% | 88.98% | 140 | 22 | 245 | 27 |
| `EMAIL` | 100.00% | 100.00% | 60 | 0 | 110 | 0 |
| `FINANCE` | 100.00% | 100.00% | 72 | 0 | 112 | 0 |
| `ID` | 90.00% | 93.08% | 180 | 18 | 260 | 18 |
| `IP` | 100.00% | 100.00% | 15 | 0 | 35 | 0 |
| `MEDICAL` | 95.00% | 92.38% | 40 | 2 | 105 | 8 |
| `ORG` | 71.67% | 71.20% | 60 | 17 | 125 | 36 |
| `PERSON` | 96.88% | 96.88% | 160 | 5 | 320 | 10 |
| `PHONE` | 100.00% | 100.00% | 80 | 0 | 200 | 0 |
| `URL` | 100.00% | 100.00% | 15 | 0 | 15 | 0 |
