# 1. Cohort periods use year/month arithmetic, not `datediff`

Status: accepted

## Context
The v1.0 plan computed periods with `datediff('month', a, b)`. Postgres has no `datediff`; the
core model would have failed on its first run.

## Decision
`macros/time.sql::periods_between` uses `(year(b) - year(a)) * 12 + (month(b) - month(a))` for
months and whole-week division for weeks. `dbt.datediff` is the portable equivalent if the
warehouse ever changes.

## Consequences
Plain Postgres, covered by the dbt unit test `retention_monthly_censoring_skipped_months_and_current_cohort`
and the Online Retail II cross-check against an independent pandas computation (exact match on every cell).
