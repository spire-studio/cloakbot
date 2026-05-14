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
| Leaked pairs | 20 |
| **Pair leak rate** | **12.90%** |
| Identifying tokens | 325 |
| Leaked tokens | 20 |
| **Token leak rate** | **6.15%** |
| Alias consistency across turns | n/a |
| Multi-turn recurring entities | 0 |
| p50 turn latency | 670 ms |
| p95 turn latency | 5822 ms |
| p99 turn latency | 5880 ms |

## Per-entity-type recall

| Type | Pair recall | Token recall | Pairs | Pair leaks | Tokens | Token leaks |
|---|---:|---:|---:|---:|---:|---:|
| `ADDRESS` | 95.00% | 99.17% | 20 | 1 | 120 | 1 |
| `DATE` | 15.00% | 15.00% | 20 | 17 | 20 | 17 |
| `EMAIL` | 100.00% | 100.00% | 20 | 0 | 35 | 0 |
| `ID` | 95.00% | 95.00% | 40 | 2 | 40 | 2 |
| `IP` | 100.00% | 100.00% | 15 | 0 | 35 | 0 |
| `PERSON` | 100.00% | 100.00% | 20 | 0 | 40 | 0 |
| `PHONE` | 100.00% | 100.00% | 20 | 0 | 35 | 0 |

## First leaks (truncated to 15)

| Session | Turn | Type | Slot | Value | Leaked tokens |
|---|---:|---|---|---|---|
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:42` | 6 | `DATE` | `callback_time` | `Friday at 3:59 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:137` | 6 | `DATE` | `callback_time` | `Saturday at 2:47 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:256` | 6 | `DATE` | `callback_time` | `Saturday at 11:48 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:1024` | 6 | `DATE` | `callback_time` | `Saturday at 12:21 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:42` | 6 | `DATE` | `callback_time` | `Friday at 3:59 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:137` | 6 | `DATE` | `callback_time` | `Saturday at 2:47 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:256` | 6 | `DATE` | `callback_time` | `Saturday at 11:48 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:1024` | 6 | `DATE` | `callback_time` | `Saturday at 12:21 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:42` | 2 | `ID` | `phone_last4` | `3389` | `3389` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:42` | 6 | `DATE` | `callback_time` | `Friday at 4:00 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:1024` | 2 | `ID` | `phone_last4` | `1626` | `1626` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:42` | 4 | `ADDRESS` | `address` | `2351 Noah Knolls Suite 940, Herrerafurt, CO 72858` | `2351` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:42` | 6 | `DATE` | `callback_time` | `Friday at 4:00 PM` | `Friday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:137` | 6 | `DATE` | `callback_time` | `Saturday at 2:48 AM` | `Saturday` |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:256` | 6 | `DATE` | `callback_time` | `Saturday at 11:49 AM` | `Saturday` |

## Per-session leak summary

| Session | Pairs | Pair leaks | Pair rate | Token leak rate | Alias |
|---|---:|---:|---:|---:|---:|
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:256` | 8 | 1 | 12.50% | 5.26% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p00:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:256` | 8 | 1 | 12.50% | 5.26% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p01:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:42` | 7 | 2 | 28.57% | 13.33% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:137` | 8 | 0 | 0.00% | 0.00% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:256` | 8 | 0 | 0.00% | 0.00% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p02:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:42` | 7 | 2 | 28.57% | 13.33% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:256` | 8 | 1 | 12.50% | 5.26% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p03:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:42` | 7 | 1 | 14.29% | 6.67% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:137` | 8 | 1 | 12.50% | 5.56% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:256` | 8 | 1 | 12.50% | 5.26% | n/a |
| `eval:customer_service_account_lockout_v1:customer_service_account_lockout_v1_p04:1024` | 8 | 1 | 12.50% | 7.69% | n/a |
