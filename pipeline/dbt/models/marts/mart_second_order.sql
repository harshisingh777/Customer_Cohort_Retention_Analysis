{{ config(indexes=[{'columns': ['customer_key'], 'unique': True}, {'columns': ['cohort_month']}]) }}

-- One row per customer. days_to_second is null for customers without a second order.
select
  a.customer_key,
  a.cohort_month,
  a.acquisition_channel,
  a.country,
  a.first_category,
  a.first_order_ts_local                         as first_order_ts,
  s.order_ts_local                               as second_order_ts,
  (s.order_ts_local::date - a.first_order_date)  as days_to_second
from {{ ref('int_customer_acquisition') }} a
left join {{ ref('int_orders') }} s
  on s.customer_key = a.customer_key
 and s.order_seq = 2
