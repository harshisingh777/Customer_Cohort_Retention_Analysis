{{ config(indexes=[{'columns': ['day']}]) }}

-- Daily revenue two ways.
--   source_*: recomputed straight from the parsed raw rows in one pass: product lines minus
--             refunds, at order-date FX, for qualifying, identified orders. No identity merge,
--             no primary-line or channel joins, so a fan-out or a lost join downstream shows up.
--   mart_*:   int_orders, the single input of every customer mart (tests check marts sum to it).
-- unidentified_revenue is qualifying revenue with no customer identity (excluded by design).
with o as (
  select * from ({{ normalized_orders() }}) x
),

items as (
  select source, order_id, sum(line_amount) as gross
  from {{ ref('stg_order_items') }}
  group by 1, 2
),

refunds as (
  select source, order_id, sum(amount) as refunded
  from {{ ref('stg_refunds') }}
  where refunded_at_local::date < {{ data_cutoff() }}
  group by 1, 2
),

fx as (
  select base, date, rate from {{ source('raw', 'fx_rates') }} where quote = {{ reporting_currency() }}
),

source_orders as (
  select
    ({{ to_local('o.order_ts_utc') }})::date as day,
    (o.platform_customer_id is not null or o.email is not null) as identified,
    (coalesce(i.gross, 0) - coalesce(r.refunded, 0)) * case
      when o.currency is null or o.currency = {{ reporting_currency() }} then 1.0
      else (select f.rate from fx f where f.base = o.currency
              and f.date <= ({{ to_local('o.order_ts_utc') }})::date order by f.date desc limit 1)
    end as net
  from o
  left join items i on i.source = o.source and i.order_id = o.order_id
  left join refunds r on r.source = o.source and r.order_id = o.order_id
  where not o.is_test
    and o.status in {{ qualifying_status_list() }}
    and ({{ to_local('o.order_ts_utc') }})::date < {{ data_cutoff() }}
),

source_daily as (
  select
    day,
    count(*) filter (where identified)                       as source_orders,
    coalesce(sum(net) filter (where identified), 0)          as source_revenue,
    coalesce(sum(net) filter (where not identified), 0)      as unidentified_revenue
  from source_orders
  where net > 0
  group by 1
),

mart_daily as (
  select order_date_local as day, count(*) as mart_orders, sum(net_revenue) as mart_revenue
  from {{ ref('int_orders') }}
  group by 1
)

select
  coalesce(s.day, m.day)                                         as day,
  coalesce(s.source_orders, 0)                                   as source_orders,
  coalesce(s.source_revenue, 0)::numeric(16, 2)                  as source_revenue,
  coalesce(m.mart_orders, 0)                                     as mart_orders,
  coalesce(m.mart_revenue, 0)::numeric(16, 2)                    as mart_revenue,
  coalesce(s.unidentified_revenue, 0)::numeric(16, 2)            as unidentified_revenue,
  (coalesce(m.mart_revenue, 0) - coalesce(s.source_revenue, 0))::numeric(16, 2) as delta
from source_daily s
full outer join mart_daily m using (day)
