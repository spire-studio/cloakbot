# Cross-domain long-document leak summary — 2026-05-15

Pipeline: ``sanitize_tool_output_chunked`` (tool-output path) for the long user turn, ``PrivacyRuntime.prepare_turn`` (input path) for the follow-up user turn, on Gemma 4 E2B via vLLM. Chunker: plaintext with max_chars=6000, overlap=300.

Aggregating 3 domain template(s).

## Cross-domain headline

| Metric | Value |
|---|---:|
| Templates | 3 |
| Total sessions | 60 |
| Sessions where chunker activated (≥2 chunks) | 60 (100%) |
| Sessions with at least one chunk failure | 2 |
| Entity-turn pairs | 1790 |
| Pair leaks | 112 |
| **Cross-domain pair leak** | **6.26%** |
| Identifying tokens | 3845 |
| Token leaks | 255 |
| **Cross-domain token leak** | **6.63%** |
| Seam leaks (total tokens) | 226 |
| Seam leaks within overlap band (300c) | 0 (0%) |
| **Cross-path alias consistency (tool→input)** | **93.86%** (489/521) |
| p95 turn latency (worst across templates) | 5427 ms |

## Per template

| Domain | Template | Sessions | Chunker | Pair leak | Token leak | Seam (in band) | Cross-path alias |
|---|---|---:|---:|---:|---:|---:|---:|
| `email` | `long_email_v1` | 20 | 20/20 | 2.03% | 1.15% | 11 (0) | 100.00% (158/158) |
| `legal_correspondence` | `long_legal_correspondence_v1` | 20 | 20/20 | 9.66% | 12.31% | 169 (0) | 89.39% (160/179) |
| `tech_ticket` | `long_tech_ticket_v1` | 20 | 20/20 | 7.10% | 4.77% | 46 (0) | 92.93% (171/184) |

## Per-entity-type recall (cross-domain)

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 76.67% | 82.50% | 120 | 28 | 680 | 119 |
| `DATE` | 100.00% | 100.00% | 200 | 0 | 325 | 0 |
| `EMAIL` | 97.22% | 98.67% | 180 | 5 | 375 | 5 |
| `FINANCE` | 97.50% | 98.57% | 200 | 5 | 350 | 5 |
| `GEO` | 26.67% | 32.86% | 60 | 44 | 140 | 94 |
| `ID` | 94.33% | 96.46% | 300 | 17 | 480 | 17 |
| `ORG` | 99.29% | 99.26% | 140 | 1 | 270 | 2 |
| `PERSON` | 100.00% | 100.00% | 420 | 0 | 840 | 0 |
| `PHONE` | 96.43% | 98.31% | 140 | 5 | 355 | 6 |
| `URL` | 76.67% | 76.67% | 30 | 7 | 30 | 7 |
