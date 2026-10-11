-- One row of data-health facts for the Data page.
with o as (
  select * from {{ ref('stg_orders') }}
),

identity as (
  select
    count(*) filter (where platform_customer_id is null and email_hmac is not null) as guest_orders,
    count(*) filter (where identity_method = 'email_merged')                        as guest_orders_merged,
    count(*) filter (where identity_method = 'none')                                as orders_without_identity
  from o
),

orders as (
  select
    count(*)                                                as orders_total,
    count(*) filter (where is_qualifying)                   as orders_qualifying,
    count(*) filter (where exclusion_reason = 'test_order')             as orders_test,
    count(*) filter (where exclusion_reason = 'status')                 as orders_status_excluded,
    count(*) filter (where exclusion_reason = 'fully_refunded_or_zero') as orders_refunded_or_zero,
    count(*) filter (where exclusion_reason = 'missing_fx_rate')        as orders_missing_fx,
    count(*) filter (where exclusion_reason = 'after_cutoff')           as orders_after_cutoff,
    min(order_date_local) filter (where is_qualifying)      as first_order_date,
    max(order_date_local) filter (where is_qualifying)      as last_order_date
  from o
),

lines as (
  select
    (select count(*) from ({{ normalized_order_items() }}) n)  as lines_total,
    (select count(*) from {{ ref('stg_order_items') }})        as lines_product,
    (select count(*) from {{ ref('stg_order_items') }} where category = 'uncategorized') as lines_uncategorized
),

customers as (
  select
    count(*)                                                         as customers,
    count(*) filter (where acquisition_channel = 'unattributed')     as customers_unattributed,
    count(*) filter (where first_category = 'uncategorized')         as customers_uncategorized
  from {{ ref('int_customer_acquisition') }}
),

repeaters as (
  select count(*) as repeat_customers from {{ ref('int_orders') }} where order_seq = 2
)

select
  ({{ data_cutoff() }} - 1)                         as data_through,
  {{ data_cutoff() }}                               as cutoff_date,
  '{{ var("reporting_tz") }}'::text                 as reporting_tz,
  {{ reporting_currency() }}::text                  as reporting_currency,
  orders.*,
  identity.*,
  case when identity.guest_orders > 0
       then round(identity.guest_orders_merged::numeric / identity.guest_orders, 4) end as identity_merge_rate,
  lines.*,
  customers.*,
  repeaters.*,
  t.threshold_days                                  as lapse_threshold_days,
  t.derived_threshold_days,
  t.override_threshold_days,
  t.p90_gap_days,
  t.gap_count
from orders, identity, lines, customers, repeaters, {{ ref('int_lapse_threshold') }} t
