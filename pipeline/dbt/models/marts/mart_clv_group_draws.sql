{{ config(indexes=[{'columns': ['acquisition_channel', 'cohort_month']}]) }}

-- Latest fit's per-draw sums of expected 12-month value, per acquisition cell. The API sums the
-- arrays over the selected cohorts, divides by customers and reads the 10th-90th percentiles.
with latest as (
  select model_version from {{ source('raw', 'clv_runs') }}
  order by fitted_at desc
  limit 1
)

select g.acquisition_channel, g.cohort_month, g.customers, g.draw_sums
from {{ source('raw', 'clv_group_draws') }} g
join latest using (model_version)
