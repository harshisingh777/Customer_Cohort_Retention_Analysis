# 6. Predicted LTV: BG/NBD + Gamma-Gamma (PyMC-Marketing), holdout-validated, shown as a range

Status: accepted

## Context
`lifetimes` is unmaintained; regression-based LTV ignores dropout; a point estimate breeds false
confidence.

## Decision
- Weekly fit in the worker with PyMC-Marketing (MCMC, 2 chains x 400 draws by default).
- Holdout: calibrate to cutoff - 180 days, predict 180 days, compare per cohort; MAPE on the Data
  page. Above 30% the API hides predictions and says why.
- Per customer, the range is a *predictive* interval: for each posterior draw, simulate alive or
  not (P(alive)), the order count given alive (gamma-Poisson around the conditional mean, shape
  r + x) and spend per order (Gamma-Gamma with the customer's posterior rate). An earlier version
  used only posterior parameter uncertainty and produced implausibly tight ranges (GBP 258k-260k
  for one customer); the predictive interval gives GBP 182k-344k.
- Per group (channel), the range is the uncertainty of the group *average*: the fit writes
  per-draw sums per (channel, cohort month). They are additive, so the API sums them under any
  date filter and reads quantiles.
- Outputs land in `raw.clv_*` and reach the marts through the normal build-audit-publish refresh.

## Consequences
A fit takes about 1-2 minutes on Online Retail II (5.8k customers). Holdout MAPE there is about 21%.
