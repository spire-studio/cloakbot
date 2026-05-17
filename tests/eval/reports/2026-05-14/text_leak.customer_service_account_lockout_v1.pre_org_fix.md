# Text leak eval — 2026-05-14

- **Template:** `customer_service_account_lockout_v1`
- **Variants:** 5 (paraphrased; slots preserved)
- **Seeds per variant:** 4
- **Total sessions:** 20
- **Detector:** google/gemma-4-e2b-it via vLLM @ http://8.131.77.138:8001/v1

Leaks are measured at two granularities. A **pair** is one (entity, user turn). A pair leaks if ANY identifying token from the entity reaches prepared text. **Token leak rate** is the fraction of identifying tokens that escaped — sharper when a multi-token entity (like a full address) is only partially masked.

## Aggregate

| Metric | Value |
|---|---:|
| Entity-turn pairs | 155 |
| Leaked pairs | 17 |
| **Pair leak rate** | **10.97%** |
| Identifying tokens | 325 |
| Leaked tokens | 17 |
| **Token leak rate** | **5.23%** |
| Alias consistency across turns | n/a |
| Multi-turn recurring entities | 0 |
| p50 turn latency | 681 ms |
| p95 turn latency | 5738 ms |
| p99 turn latency | 5924 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 100.00% | 100.00% | 20 | 0 | 120 | 0 |
| `DATE` | 25.00% | 25.00% | 20 | 15 | 20 | 15 |
| `EMAIL` | 100.00% | 100.00% | 20 | 0 | 35 | 0 |
| `ID` | 95.00% | 95.00% | 40 | 2 | 40 | 2 |
| `IP` | 100.00% | 100.00% | 15 | 0 | 35 | 0 |
| `PERSON` | 100.00% | 100.00% | 20 | 0 | 40 | 0 |
| `PHONE` | 100.00% | 100.00% | 20 | 0 | 35 | 0 |

## First leaks (truncated to 15)

| Session | Turn | Type | Slot | Value | Leaked tokens |
|---|---:|---|---|---|---|
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:42` | 6 | `DATE` | `callback_time` | `Friday at 3:36 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:137` | 6 | `DATE` | `callback_time` | `Saturday at 2:24 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:256` | 6 | `DATE` | `callback_time` | `Saturday at 11:26 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:1024` | 6 | `DATE` | `callback_time` | `Friday at 11:58 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:42` | 6 | `DATE` | `callback_time` | `Friday at 3:37 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:137` | 6 | `DATE` | `callback_time` | `Saturday at 2:25 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:1024` | 6 | `DATE` | `callback_time` | `Friday at 11:58 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:42` | 2 | `ID` | `phone_last4` | `3389` | `3389` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:42` | 6 | `DATE` | `callback_time` | `Friday at 3:37 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:137` | 6 | `DATE` | `callback_time` | `Saturday at 2:25 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:256` | 6 | `DATE` | `callback_time` | `Saturday at 11:26 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:1024` | 6 | `DATE` | `callback_time` | `Friday at 11:59 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:42` | 6 | `DATE` | `callback_time` | `Friday at 3:37 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:137` | 6 | `DATE` | `callback_time` | `Saturday at 2:25 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:256` | 6 | `DATE` | `callback_time` | `Saturday at 11:26 AM` | `Saturday` |

## Per-session leak summary

| Session | Pairs | Pair leaks | Pair rate | Token leak rate | Alias |
|---|---:|---:|---:|---:|---:|
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:256` | 8 | 1 | 12.50% | 5.26% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:256` | 8 | 0 | 0.00% | 0.00% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:137` | 8 | 0 | 0.00% | 0.00% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:256` | 8 | 0 | 0.00% | 0.00% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:1024` | 8 | 0 | 0.00% | 0.00% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:256` | 8 | 1 | 12.50% | 5.26% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:256` | 8 | 1 | 12.50% | 5.26% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:1024` | 8 | 2 | 25.00% | 15.38% | n/a |
