{{ config(indexes=[{'columns': ['level', 'cohort_month']}, {'columns': ['acquisition_channel', 'country', 'first_category']}]) }}

-- Which first purchase produces customers who come back. "Repeat within 90 days" counts a
-- second qualifying order on days 0-89 after the first, among customers whose first order is
-- at least 90 days before the cutoff (so every counted customer had the full window).
with base as (
  select
    a.*,
    ({{ data_cutoff() }} - a.first_order_date) >= 90                       as eligible_90d,
    s.order_date_local is not null
      and (s.order_date_local - a.first_order_date) < 90                   as repeat_90d
  from {{ ref('int_customer_acquisition') }} a
  left join {{ ref('int_orders') }} s
    on s.customer_key = a.customer_key
   and s.order_seq = 2
)

select
  'category'                                         as level,
  first_category                                     as item_id,
  first_category                                     as item_label,
  cohort_month, acquisition_channel, country, first_category,
  count(*)                                           as first_buyers,
  count(*) filter (where eligible_90d)               as eligible_90d,
  count(*) filter (where eligible_90d and repeat_90d) as repeat_90d
from base
group by 1, 2, 3, 4, 5, 6, 7

union all

select
  'product',
  coalesce(first_product_id, 'unknown'),
  max(coalesce(first_product_name, first_product_id, 'Unknown product')),
  cohort_month, acquisition_channel, country, first_category,
  count(*),
  count(*) filter (where eligible_90d),
  count(*) filter (where eligible_90d and repeat_90d)
from base
group by 1, 2, 4, 5, 6, 7
