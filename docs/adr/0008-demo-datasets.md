# 8. Real datasets only: Online Retail II is the primary demo; Olist is the low-repeat stress case

Status: accepted

## Decision
- Online Retail II (UCI 502): real repeat behaviour. Cleaning lives in an adapter: rows without a
  Customer ID are dropped and counted (23% of lines); "C" invoices are allocated to the same
  customer's earlier purchases of the same stock code as refunds; non-product codes are excluded
  by the dbt seed; UK local time is converted to UTC. The cutoff is pinned to the day after the
  last invoice.
- Olist uses `customer_unique_id` (never the per-order `customer_id`); the files go in
  `data/olist/` because Kaggle needs an account.

## Consequences
The Dec 2009 cohort of Online Retail II includes every customer already active before the data
starts (acquisition is left-censored), and many customers are wholesalers, so repeat rates run
higher than a typical D2C store. The marts match an independent pandas computation of the
heatmap exactly (300 cells, 0.0 points maximum difference).

No synthetic data ships with the product or its tests: correctness is checked on real data
(Online Retail II against an independent pandas computation) and with small dbt unit-test fixtures.
