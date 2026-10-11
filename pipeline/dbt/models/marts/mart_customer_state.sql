{{ config(indexes=[
    {'columns': ['customer_key'], 'unique': True},
    {'columns': ['rfm_segment']},
    {'columns': ['cohort_month']},
    {'columns': ['acquisition_channel', 'country', 'first_category']}
]) }}

with acq as (
  select * from {{ ref('int_customer_acquisition') }}
),

threshold as (
  select threshold_days from {{ ref('int_lapse_threshold') }}
),

agg as (
  select
    o.customer_key,
    count(*)                                   as orders,
    sum(o.net_revenue)                         as net_revenue,
    max(o.order_date_local)                    as last_order_date,
    sum(o.net_revenue) filter (where o.order_date_local < a.first_order_date + 90)  as rev_90,
    sum(o.net_revenue) filter (where o.order_date_local < a.first_order_date + 180) as rev_180,
    sum(o.net_revenue) filter (where o.order_date_local < a.first_order_date + 365) as rev_365
  from {{ ref('int_orders') }} o
  join acq a using (customer_key)
  group by 1
),

state as (
  select
    a.customer_key,
    a.cohort_month,
    a.acquisition_channel,
    a.country,
    a.first_category,
    a.first_product_name,
    a.first_order_date,
    g.last_order_date,
    g.orders,
    g.net_revenue::numeric(14, 2)                                           as net_revenue,
    (g.net_revenue / g.orders)::numeric(14, 2)                              as avg_order_value,
    ({{ data_cutoff() }} - 1) - g.last_order_date                           as days_since_last,
    {{ data_cutoff() }} - a.first_order_date                                as age_days,
    (({{ data_cutoff() }} - 1) - g.last_order_date) > t.threshold_days      as is_lapsed,
    case when {{ data_cutoff() }} - a.first_order_date >= 90  then g.rev_90  end::numeric(14, 2) as ltv_90d,
    case when {{ data_cutoff() }} - a.first_order_date >= 180 then g.rev_180 end::numeric(14, 2) as ltv_180d,
    case when {{ data_cutoff() }} - a.first_order_date >= 365 then g.rev_365 end::numeric(14, 2) as ltv_365d
  from acq a
  join agg g using (customer_key)
  cross join threshold t
),

scored as (
  select
    s.*,
    -- Recency and Monetary by quintile; 5 = most recent / highest spend.
    ntile(5) over (order by s.days_since_last desc, s.customer_key asc) as rfm_r,
    -- Frequency by fixed bands: most customers have one order, so quintiles collapse on ties.
    case
      when s.orders >= 6 then 5
      when s.orders >= 4 then 4
      when s.orders = 3 then 3
      when s.orders = 2 then 2
      else 1
    end                                                              as rfm_f,
    ntile(5) over (order by s.net_revenue, s.customer_key)           as rfm_m
  from state s
)

select
  *,
  {{ rfm_segment('rfm_r', 'rfm_f') }} as rfm_segment
from scored
