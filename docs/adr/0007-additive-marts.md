# 7. Filter dimensions are frozen at acquisition, so marts are additive

Status: accepted

## Context
Distinct-customer counts don't add across arbitrary filters, and precomputing every combination
explodes.

## Decision
Channel, country and first category are attributes a customer gets once, at the first qualifying
order. Each customer sits in exactly one bucket, so every filtered view is a `SUM` over a small
table. Histograms (days to second order) and RFM cells are stored as counts per value for the same
reason; CLV group ranges are stored as per-draw sums.

## Consequences
"Customers who bought category X at any point" is not a v1 filter (it is a behavioural question
that needs an on-demand query). Spend exists per channel only, so the Channels page ignores
country and category filters and says so. An API test asserts that per-channel cohort sizes sum
to the total.
