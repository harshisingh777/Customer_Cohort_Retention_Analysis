{{ config(indexes=[{'columns': ['customer_key']}]) }}

-- One row per customer per month with at least one qualifying order.
select distinct
  customer_key,
  date_trunc('month', order_ts_local)::date as activity_month
from {{ ref('int_orders') }}
