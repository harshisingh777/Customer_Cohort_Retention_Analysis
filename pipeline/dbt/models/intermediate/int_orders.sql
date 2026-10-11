{{ config(indexes=[{'columns': ['customer_key', 'order_seq']}, {'columns': ['order_date_local']}]) }}

-- Qualifying orders of identified customers, numbered per customer.
-- Every customer metric is built from this model and nothing else.
select
  source,
  order_id,
  customer_key,
  order_ts_local,
  order_date_local,
  net_revenue,
  primary_category,
  primary_product_id,
  primary_product_name,
  acquisition_channel,
  country,
  row_number() over (
    partition by customer_key
    order by order_ts_local, order_id
  )                                                         as order_seq,
  lead(order_ts_local) over (
    partition by customer_key
    order by order_ts_local, order_id
  )                                                         as next_order_ts_local
from {{ ref('stg_orders') }}
where is_qualifying
  and customer_key is not null
