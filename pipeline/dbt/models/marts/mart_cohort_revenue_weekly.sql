{{ config(indexes=[
    {'columns': ['cohort_week', 'period_number']},
    {'columns': ['acquisition_channel', 'country', 'first_category']}
]) }}

select
  cohort_week,
  acquisition_channel,
  country,
  first_category,
  period_number,
  cohort_customers,
  net_revenue
from {{ ref('mart_cohort_retention_weekly') }}
