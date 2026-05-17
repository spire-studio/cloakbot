# Long-document leak eval — 2026-05-15

- **Template:** `long_legal_correspondence_v1`
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
| Entity-turn pairs | 580 |
| Leaked pairs | 56 |
| **Pair leak rate** | **9.66%** |
| Identifying tokens | 1495 |
| Leaked tokens | 184 |
| **Token leak rate** | **12.31%** |
| Seam leaks (total) | 169 |
| Seam leaks within overlap band (300c) | 0 |
| Cross-path alias consistency (tool→input) | 89.39% (160/179) |
| Alias consistency across turns | 89.39% |
| p50 turn latency | 1834 ms |
| p95 turn latency | 3369 ms |
| p99 turn latency | 3573 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 65.00% | 72.33% | 80 | 28 | 430 | 119 |
| `DATE` | 100.00% | 100.00% | 60 | 0 | 110 | 0 |
| `EMAIL` | 87.50% | 95.00% | 40 | 5 | 100 | 5 |
| `FINANCE` | 100.00% | 100.00% | 60 | 0 | 120 | 0 |
| `GEO` | 10.00% | 10.00% | 20 | 18 | 60 | 54 |
| `ID` | 100.00% | 100.00% | 40 | 0 | 80 | 0 |
| `ORG` | 100.00% | 100.00% | 80 | 0 | 170 | 0 |
| `PERSON` | 100.00% | 100.00% | 160 | 0 | 320 | 0 |
| `PHONE` | 87.50% | 94.29% | 40 | 5 | 105 | 6 |

## Seam attribution (long-turn leaks only, truncated to 20)

| Session | Token | Offset | Nearest seam | Distance | In overlap band? | Type | Slot |
|---|---|---:|---:|---:|:---:|---|---|
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `1316` | 226 | 7269 | 7043 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `Chavez` | 231 | 7269 | 7038 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `Village` | 238 | 7269 | 7031 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `Franciscostad` | 247 | 7269 | 7022 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `88342` | 265 | 7269 | 7004 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `Middlesex` | 859 | 7269 | 6410 | no | `GEO` | `incident_location` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `County` | 869 | 7269 | 6400 | no | `GEO` | `incident_location` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | `Massachusetts` | 877 | 7269 | 6392 | no | `GEO` | `incident_location` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `3387` | 240 | 7379 | 7139 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `Claudia` | 245 | 7379 | 7134 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `Mews` | 253 | 7379 | 7126 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `South` | 259 | 7379 | 7120 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `Kimberly` | 265 | 7379 | 7114 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `36004` | 278 | 7379 | 7101 | no | `ADDRESS` | `recipient_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `Middlesex` | 896 | 7379 | 6483 | no | `GEO` | `incident_location` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `County` | 906 | 7379 | 6473 | no | `GEO` | `incident_location` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | `Massachusetts` | 914 | 7379 | 6465 | no | `GEO` | `incident_location` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:256` | `Cameron` | 6641 | 7335 | 694 | no | `ADDRESS` | `sender_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:256` | `Neck` | 6649 | 7335 | 686 | no | `ADDRESS` | `sender_address` |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:256` | `East` | 6655 | 7335 | 680 | no | `ADDRESS` | `sender_address` |

## Per-session summary

| Session | Chars | Chunks | Failed? | Pair leaks | Token leak rate | Cross-path alias |
|---|---:|---:|:---:|---:|---:|---|
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:42` | 7269 | 2 | no | 2 | 11.11% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:137` | 7379 | 2 | no | 2 | 11.39% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:256` | 7335 | 2 | no | 3 | 15.79% | 7/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p00:1024` | 7280 | 2 | no | 5 | 18.06% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p01:42` | 7227 | 2 | no | 2 | 11.11% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p01:137` | 7337 | 2 | no | 2 | 11.39% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p01:256` | 7293 | 2 | no | 2 | 10.53% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p01:1024` | 7238 | 2 | no | 5 | 20.83% | 7/8 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p02:42` | 7380 | 2 | no | 2 | 11.11% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p02:137` | 7490 | 2 | no | 2 | 11.39% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p02:256` | 7446 | 2 | no | 3 | 13.16% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p02:1024` | 7391 | 2 | no | 5 | 18.06% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p03:42` | 7278 | 2 | no | 2 | 11.11% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p03:137` | 7388 | 2 | no | 2 | 5.06% | 9/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p03:256` | 7344 | 2 | no | 2 | 10.53% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p03:1024` | 7289 | 2 | no | 5 | 18.06% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p04:42` | 7361 | 2 | no | 1 | 6.94% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p04:137` | 7471 | 2 | no | 3 | 13.92% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p04:256` | 7427 | 2 | no | 2 | 9.21% | 8/9 |
| `eval:long_legal_correspondence_v1:long_legal_correspondence_v1_p04:1024` | 7372 | 2 | no | 4 | 8.33% | 9/9 |
