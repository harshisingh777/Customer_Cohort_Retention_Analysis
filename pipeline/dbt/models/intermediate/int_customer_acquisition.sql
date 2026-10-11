{{ config(indexes=[{'columns': ['customer_key'], 'unique': True}, {'columns': ['cohort_month']}]) }}

-- One row per customer, attributes frozen at the first qualifying order.
-- Because each customer lands in exactly one (channel, country, first_category) bucket,
-- every cohort mart is additive across these dimensions (spec §5.5).
with ranked as (
  select
    customer_key,
    order_id,
    order_ts_local,
    acquisition_channel,
    country,
    primary_category,
    primary_product_id,
    primary_product_name,
    order_seq
  from {{ ref('int_orders') }}
)

select
  customer_key,
  order_id                                       as first_order_id,
  order_ts_local                                 as first_order_ts_local,
  order_ts_local::date                           as first_order_date,
  date_trunc('month', order_ts_local)::date      as cohort_month,
  date_trunc('week',  order_ts_local)::date      as cohort_week,
  coalesce(acquisition_channel, 'unattributed')  as acquisition_channel,
  coalesce(country, 'unknown')                   as country,
  coalesce(primary_category, 'uncategorized')    as first_category,
  primary_product_id                             as first_product_id,
  primary_product_name                           as first_product_name
from ranked
where order_seq = 1
