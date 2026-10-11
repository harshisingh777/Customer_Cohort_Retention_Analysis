{{ config(indexes=[{'columns': ['cohort_month']}, {'columns': ['acquisition_channel', 'country', 'first_category']}]) }}

-- Additive Recency x Frequency grid. Cell shade = SUM(net_revenue) / SUM(customers).
select
  rfm_r,
  rfm_f,
  rfm_segment,
  cohort_month,
  acquisition_channel,
  country,
  first_category,
  count(*)                                   as customers,
  sum(net_revenue)::numeric(16, 2)           as net_revenue,
  count(*) filter (where is_lapsed)          as lapsed_customers
from {{ ref('mart_customer_state') }}
group by 1, 2, 3, 4, 5, 6, 7
