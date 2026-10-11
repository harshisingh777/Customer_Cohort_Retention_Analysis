{{ config(indexes=[{'columns': ['month_end']}, {'columns': ['acquisition_channel', 'country', 'first_category']}]) }}

-- Lapse rate as of each month end: among customers acquired by then, the share whose last
-- qualifying order on or before that day is older than the lapse threshold.
with threshold as (
  select threshold_days from {{ ref('int_lapse_threshold') }}
),

days as (
  select distinct customer_key, order_date_local as order_date
  from {{ ref('int_orders') }}
),

-- Each order date "covers" the customer until their next order date.
spans as (
  select
    customer_key,
    order_date                                                    as start_date,
    coalesce(lead(order_date) over (partition by customer_key order by order_date),
             date '9999-12-31')                                   as end_date
  from days
),

month_ends as (
  select (m + interval '1 month - 1 day')::date as month_end
  from generate_series(
    (select min(cohort_month) from {{ ref('int_customer_acquisition') }}),
    {{ last_complete('month') }},
    interval '1 month'
  ) m
)

select
  me.month_end,
  a.acquisition_channel,
  a.country,
  a.first_category,
  count(*)                                                             as base_customers,
  count(*) filter (where me.month_end - s.start_date > t.threshold_days) as lapsed_customers
from month_ends me
join spans s
  on s.start_date <= me.month_end
 and me.month_end < s.end_date
join {{ ref('int_customer_acquisition') }} a using (customer_key)
cross join threshold t
group by 1, 2, 3, 4
