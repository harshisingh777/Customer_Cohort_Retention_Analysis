{{ config(indexes=[{'columns': ['customer_key']}]) }}

-- One row per customer per ISO week (Monday start) with at least one qualifying order.
select distinct
  customer_key,
  date_trunc('week', order_ts_local)::date as activity_week
from {{ ref('int_orders') }}
