# 9. Write-audit-publish with an atomic schema swap

Status: accepted

## Decision
One `refresh` job: advisory lock -> ingest from cursors (3-day overlap) -> `dbt build` into
`analytics_build`/`pii_build` -> audit (every dbt test and invariant; reconciliation within 0.5%
over 90 days; no mart shrinking by more than 20% without an override) -> in one transaction with
`lock_timeout = 5s`: rename `analytics` to `analytics_prev` and `analytics_build` to `analytics`
(same for `pii`), drop prev, insert `ops.data_versions`, `NOTIFY data_published`. Lock timeouts
retry three times, then fail without touching `analytics`.

## Consequences
A failed or half-finished run never reaches the dashboard; the Data page shows "stale since".
Tests prove it with a deliberately failing dbt test (`assert_audit_canary`), a forced shrink and a
forced reconciliation miss. Staging is rebuilt in full each run rather than incrementally: with
schema swaps an incremental table would first have to be cloned into the build schema, and a
full Online Retail II build takes about 30 s (budget: 3 min), so this is deferred until a run
exceeds 10 minutes.
