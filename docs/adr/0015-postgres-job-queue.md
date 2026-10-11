# 15. One worker with a Postgres-backed queue; no Dagster, Redis or Celery

Status: accepted

## Decision
`ops.jobs` is claimed with `FOR UPDATE SKIP LOCKED`, retried with exponential backoff (max 3),
pruned after 30 days; stale `running` jobs are requeued after 2 hours. The worker schedules one
refresh per day at a local time and one CLV fit per week; `(kind, scheduled_for)` is unique, so
restarts and double-schedules can't duplicate runs. A refresh audit failure is not retried
(the same data would fail again); the run is recorded and alerted.

## Consequences
Revisit at multi-tenant scale.
