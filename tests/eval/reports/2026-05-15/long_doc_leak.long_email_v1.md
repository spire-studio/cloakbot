# Long-document leak eval — 2026-05-15

- **Template:** `long_email_v1`
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
| Sessions with at least one chunk failure | 2 |
| p50 chunks per long doc | 2.0 |
| Max chunks per long doc | 2 |
| Entity-turn pairs | 590 |
| Leaked pairs | 12 |
| **Pair leak rate** | **2.03%** |
| Identifying tokens | 1135 |
| Leaked tokens | 13 |
| **Token leak rate** | **1.15%** |
| Seam leaks (total) | 11 |
| Seam leaks within overlap band (300c) | 0 |
| Cross-path alias consistency (tool→input) | 100.00% (158/158) |
| Alias consistency across turns | 100.00% |
| p50 turn latency | 2030 ms |
| p95 turn latency | 4160 ms |
| p99 turn latency | 30005 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 100.00% | 100.00% | 20 | 0 | 110 | 0 |
| `DATE` | 100.00% | 100.00% | 80 | 0 | 155 | 0 |
| `EMAIL` | 100.00% | 100.00% | 80 | 0 | 160 | 0 |
| `FINANCE` | 100.00% | 100.00% | 120 | 0 | 200 | 0 |
| `ID` | 95.00% | 95.00% | 80 | 4 | 80 | 4 |
| `ORG` | 95.00% | 95.00% | 20 | 1 | 40 | 2 |
| `PERSON` | 100.00% | 100.00% | 140 | 0 | 280 | 0 |
| `PHONE` | 100.00% | 100.00% | 40 | 0 | 100 | 0 |
| `URL` | 30.00% | 30.00% | 10 | 7 | 10 | 7 |

## Seam attribution (long-turn leaks only, truncated to 20)

| Session | Token | Offset | Nearest seam | Distance | In overlap band? | Type | Slot |
|---|---|---:|---:|---:|:---:|---|---|
| `eval:long_email_v1:long_email_v1_p00:42` | `josephwright` | 3817 | 7613 | 3796 | no | `URL` | `pager_handle` |
| `eval:long_email_v1:long_email_v1_p01:42` | `josephwright` | 3818 | 7614 | 3796 | no | `URL` | `pager_handle` |
| `eval:long_email_v1:long_email_v1_p02:42` | `josephwright` | 3777 | 7573 | 3796 | no | `URL` | `pager_handle` |
| `eval:long_email_v1:long_email_v1_p02:256` | `vgarcia` | 3775 | 7561 | 3786 | no | `URL` | `pager_handle` |
| `eval:long_email_v1:long_email_v1_p03:42` | `josephwright` | 3783 | 7579 | 3796 | no | `URL` | `pager_handle` |
| `eval:long_email_v1:long_email_v1_p04:42` | `James` | 765 | 7493 | 6728 | no | `ORG` | `previous_employer` |
| `eval:long_email_v1:long_email_v1_p04:42` | `Group` | 771 | 7493 | 6722 | no | `ORG` | `previous_employer` |
| `eval:long_email_v1:long_email_v1_p04:42` | `josephwright` | 3697 | 7493 | 3796 | no | `URL` | `pager_handle` |
| `eval:long_email_v1:long_email_v1_p04:256` | `vgarcia` | 3710 | 7496 | 3786 | no | `URL` | `pager_handle` |
| `eval:long_email_v1:long_email_v1_p04:1024` | `75821388` | 3511 | 7605 | 4094 | no | `ID` | `it_account_id` |
| `eval:long_email_v1:long_email_v1_p04:1024` | `687203` | 3541 | 7605 | 4064 | no | `ID` | `badge_number` |

## Per-session summary

| Session | Chars | Chunks | Failed? | Pair leaks | Token leak rate | Cross-path alias |
|---|---:|---:|:---:|---:|---:|---|
| `eval:long_email_v1:long_email_v1_p00:42` | 7613 | 2 | no | 1 | 1.67% | 8/8 |
| `eval:long_email_v1:long_email_v1_p00:137` | 7634 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p00:256` | 7618 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p00:1024` | 7721 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p01:42` | 7614 | 2 | yes | 1 | 1.67% | 8/8 |
| `eval:long_email_v1:long_email_v1_p01:137` | 7635 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p01:256` | 7619 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p01:1024` | 7722 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p02:42` | 7573 | 2 | no | 1 | 1.67% | 8/8 |
| `eval:long_email_v1:long_email_v1_p02:137` | 7595 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p02:256` | 7561 | 2 | no | 1 | 1.85% | 8/8 |
| `eval:long_email_v1:long_email_v1_p02:1024` | 7687 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p03:42` | 7579 | 2 | no | 1 | 1.67% | 8/8 |
| `eval:long_email_v1:long_email_v1_p03:137` | 7599 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p03:256` | 7582 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p03:1024` | 7691 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p04:42` | 7493 | 2 | no | 2 | 5.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p04:137` | 7513 | 2 | no | 0 | 0.00% | 8/8 |
| `eval:long_email_v1:long_email_v1_p04:256` | 7496 | 2 | no | 1 | 1.85% | 8/8 |
| `eval:long_email_v1:long_email_v1_p04:1024` | 7605 | 2 | yes | 4 | 7.02% | 6/6 |
