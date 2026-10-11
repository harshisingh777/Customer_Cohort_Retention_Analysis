# 4. Report lapse, derived from the store's own purchase gaps, plus P(alive)

Status: accepted

## Context
`1 - retention` is not churn: customers skip months and come back.

## Decision
The lapse threshold is the 90th percentile of gaps between consecutive orders (customers with 2+
orders), clamped to 60-365 days, overridable by an admin. A customer is lapsed when their last
order is older than the threshold; lapse rate is the churn figure. BG/NBD P(alive) marks
"drifting" customers (P(alive) < 0.5 and not yet lapsed).

## Consequences
BG/NBD only lets customers drop out after a repeat purchase, so one-order customers always score
P(alive) = 1; the lapse rule is what flags them. This caveat is in `metrics.yml`.
