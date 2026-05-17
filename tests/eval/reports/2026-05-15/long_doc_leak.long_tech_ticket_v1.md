# Long-document leak eval — 2026-05-15

- **Template:** `long_tech_ticket_v1`
- **Variants:** 5
- **Seeds per variant:** 4
- **Total sessions:** 20
- **Detector:** google/gemma-4-e2b-it via vLLM @ http://8.131.77.138:8001/v1
- **Chunker:** plaintext, max_chars=6000, overlap=300

Long-document content is driven through ``sanitize_tool_output_chunked`` (the chunker-backed tool-output path); short follow-up turns go through ``prepare_turn`` on the same session, so vault carryover across the tool→input path boundary is testable.

## Aggregate

| Metric | Value |
|---|---:|
| Sessions | 20 |
| Sessions where chunker activated (≥2 chunks) | 20 |
| Sessions with at least one chunk failure | 0 |
| p50 chunks per long doc | 2.0 |
| Max chunks per long doc | 2 |
| Entity-turn pairs | 620 |
| Leaked pairs | 44 |
| **Pair leak rate** | **7.10%** |
| Identifying tokens | 1215 |
| Leaked tokens | 58 |
| **Token leak rate** | **4.77%** |
| Seam leaks (total) | 46 |
| Seam leaks within overlap band (300c) | 0 |
| Cross-path alias consistency (tool→input) | 92.93% (171/184) |
| Alias consistency across turns | 92.93% |
| p50 turn latency | 1959 ms |
| p95 turn latency | 5427 ms |
| p99 turn latency | 5964 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 100.00% | 100.00% | 20 | 0 | 140 | 0 |
| `DATE` | 100.00% | 100.00% | 60 | 0 | 60 | 0 |
| `EMAIL` | 100.00% | 100.00% | 60 | 0 | 115 | 0 |
| `FINANCE` | 75.00% | 83.33% | 20 | 5 | 30 | 5 |
| `GEO` | 35.00% | 50.00% | 40 | 26 | 80 | 40 |
| `ID` | 92.78% | 95.94% | 180 | 13 | 320 | 13 |
| `ORG` | 100.00% | 100.00% | 40 | 0 | 60 | 0 |
| `PERSON` | 100.00% | 100.00% | 120 | 0 | 240 | 0 |
| `PHONE` | 100.00% | 100.00% | 60 | 0 | 150 | 0 |
| `URL` | 100.00% | 100.00% | 20 | 0 | 20 | 0 |

## Seam attribution (long-turn leaks only, truncated to 20)

| Session | Token | Offset | Nearest seam | Distance | In overlap band? | Type | Slot |
|---|---|---:|---:|---:|:---:|---|---|
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:42` | `prod` | 489 | 7703 | 7214 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:137` | `prod` | 489 | 7688 | 7199 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:256` | `457` | 2308 | 7628 | 5320 | no | `ID` | `product_version` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:256` | `780` | 2470 | 7628 | 5158 | no | `ID` | `last_known_good_version` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:256` | `prod` | 480 | 7628 | 7148 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:256` | `200` | 3615 | 7628 | 4013 | no | `FINANCE` | `business_impact` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:1024` | `prod` | 475 | 7662 | 7187 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:1024` | `southeast` | 1030 | 7662 | 6632 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:42` | `prod` | 136 | 8296 | 8160 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:42` | `8849` | 1588 | 8296 | 6708 | no | `ID` | `error_code` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:137` | `prod` | 136 | 8285 | 8149 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:137` | `east` | 1548 | 8285 | 6737 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:256` | `prod` | 130 | 8221 | 8091 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:256` | `0121` | 1572 | 8221 | 6649 | no | `ID` | `error_code` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:256` | `200` | 4023 | 8221 | 4198 | no | `FINANCE` | `business_impact` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:1024` | `prod` | 132 | 8257 | 8125 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:1024` | `southeast` | 1532 | 8257 | 6725 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:1024` | `5821` | 1573 | 8257 | 6684 | no | `ID` | `error_code` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p02:42` | `prod` | 330 | 7791 | 7461 | no | `GEO` | `environment` |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p02:42` | `8849` | 1573 | 7791 | 6218 | no | `ID` | `error_code` |

## Per-session summary

| Session | Chars | Chunks | Failed? | Pair leaks | Token leak rate | Cross-path alias |
|---|---:|---:|:---:|---:|---:|---|
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:42` | 7703 | 2 | no | 1 | 1.54% | 10/10 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:137` | 7688 | 2 | no | 1 | 1.64% | 10/10 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:256` | 7628 | 2 | no | 4 | 6.67% | 9/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p00:1024` | 7662 | 2 | no | 1 | 3.51% | 8/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:42` | 8296 | 2 | no | 2 | 3.08% | 9/10 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:137` | 8285 | 2 | no | 2 | 6.56% | 9/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:256` | 8221 | 2 | no | 3 | 5.00% | 8/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p01:1024` | 8257 | 2 | no | 2 | 5.26% | 7/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p02:42` | 7791 | 2 | no | 2 | 3.08% | 9/10 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p02:137` | 7770 | 2 | no | 3 | 8.20% | 8/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p02:256` | 7710 | 2 | no | 3 | 5.00% | 8/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p02:1024` | 7744 | 2 | no | 2 | 3.51% | 8/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p03:42` | 7840 | 2 | no | 1 | 1.54% | 10/10 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p03:137` | 7814 | 2 | no | 3 | 8.20% | 8/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p03:256` | 7750 | 2 | no | 2 | 3.33% | 9/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p03:1024` | 7784 | 2 | no | 3 | 8.77% | 7/8 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p04:42` | 7966 | 2 | no | 1 | 1.54% | 10/10 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p04:137` | 7938 | 2 | no | 2 | 6.56% | 9/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p04:256` | 7877 | 2 | no | 3 | 5.00% | 8/9 |
| `eval:long_tech_ticket_v1:long_tech_ticket_v1_p04:1024` | 7913 | 2 | no | 3 | 8.77% | 7/8 |
