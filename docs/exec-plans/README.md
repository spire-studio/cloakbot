# Execution Plans

Use an execution plan for work that has multiple dependent steps, carries
architectural risk, or spans more than one subsystem.

## Layout

- `active/` - in-progress plans.
- `completed/` - finished plans retained for design history.
- `tech-debt-tracker.md` - known gaps and cleanup targets.

## Plan Template

```md
# <short task name>

## Goal

One sentence describing the desired end state.

## Assumptions

- ...

## Steps

1. <step> -> verify: <check>
2. <step> -> verify: <check>

## Decisions

- YYYY-MM-DD: <decision and reason>

## Validation

- [ ] <command or manual check>
```

Move completed plans into `completed/` and update the debt tracker when a plan
adds, resolves, or reclassifies known debt.
