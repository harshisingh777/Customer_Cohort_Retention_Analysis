-- The latest CLV fit and its holdout check, per cohort. The API hides predicted LTV when
-- holdout MAPE exceeds 30% (spec §9.6).
with latest as (
  select * from {{ source('raw', 'clv_runs') }}
  order by fitted_at desc
  limit 1
)

select
  l.model_version,
  l.fitted_at,
  l.cutoff_date,
  l.method,
  l.n_customers,
  l.holdout_days,
  l.holdout_mape,
  h.cohort_month,
  h.customers,
  h.predicted_revenue,
  h.actual_revenue
from latest l
left join {{ source('raw', 'clv_holdout') }} h using (model_version)
