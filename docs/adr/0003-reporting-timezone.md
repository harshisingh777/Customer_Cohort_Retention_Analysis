# 3. Store UTC, bucket in the merchant's timezone

Status: accepted

## Context
A US store's 9 pm order on 31 March is 1 April in UTC; month-boundary orders land in the wrong
cohort if bucketed in UTC.

## Decision
Raw timestamps are stored as UTC (adapters convert local timestamps, e.g. Online Retail II's UK
times). `stg_orders` derives `order_ts_local` in the reporting timezone (a setting); every month,
week and day downstream uses local time. The data cutoff is a local date.

## Consequences
Changing the timezone is a definition change: `PUT /v1/settings` enqueues a full rebuild. The
dbt unit test
checks that 23:30 UTC on 31 March becomes April in Europe/London.
