{{ config(indexes=[{'columns': ['acquisition_channel', 'cohort_month']}]) }}

-- Channel x cohort month x period. CAC and payback are computed in the API from this and
-- mart_channel_spend_monthly; spend is per channel only, so channel views ignore country and
-- category filters for CAC.
with cells as (
  select
    acquisition_channel,
    cohort_month,
    period_number,
    sum(cohort_customers)  as new_customers,
    sum(net_revenue)       as net_revenue
  from {{ ref('mart_cohort_retention_monthly') }}
  group by 1, 2, 3
)

select
  c.*,
  (sum(c.net_revenue) over (
     partition by c.acquisition_channel, c.cohort_month
     order by c.period_number
     rows between unbounded preceding and current row
   ) / nullif(c.new_customers, 0))::numeric(14, 4) as cum_net_revenue_per_customer
from cells c
