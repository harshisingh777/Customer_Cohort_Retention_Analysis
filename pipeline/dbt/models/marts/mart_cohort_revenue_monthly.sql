{{ config(indexes=[
    {'columns': ['cohort_month', 'period_number']},
    {'columns': ['acquisition_channel', 'country', 'first_category']}
]) }}

-- Revenue retention, month N = SUM(net_revenue at N) / SUM(net_revenue at 0). Same grain and
-- observability as the retention mart.
select
  cohort_month,
  acquisition_channel,
  country,
  first_category,
  period_number,
  cohort_customers,
  net_revenue
from {{ ref('mart_cohort_retention_monthly') }}
