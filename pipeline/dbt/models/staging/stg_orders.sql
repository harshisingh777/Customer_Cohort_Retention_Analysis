{{ config(indexes=[
    {'columns': ['customer_key']},
    {'columns': ['order_date_local']},
    {'columns': ['source', 'order_id'], 'unique': True}
]) }}

with orders as (
  select o.*, {{ hmac_email('o.email') }} as email_hmac
  from ({{ normalized_orders() }}) o
),

item_totals as (
  select source, order_id, sum(line_amount) as gross_amount
  from {{ ref('stg_order_items') }}
  group by 1, 2
),

-- The line with the largest share of the order's revenue names its category and product.
primary_line as (
  select distinct on (source, order_id)
    source,
    order_id,
    category                        as primary_category,
    coalesce(sku, product_name)     as primary_product_id,
    coalesce(product_name, sku)     as primary_product_name
  from {{ ref('stg_order_items') }}
  order by source asc, order_id asc, line_amount desc, line_id asc
),

refund_totals as (
  select source, order_id, sum(amount) as refunded_amount
  from {{ ref('stg_refunds') }}
  where refunded_at_local::date < {{ data_cutoff() }}
  group by 1, 2
),

-- Who owns an email: registered customers, from the customer table and from their own orders.
email_owner as (
  select email_hmac, min(platform_customer_id) as owner_id
  from (
    select email_hmac, platform_customer_id from {{ ref('stg_customers') }}
    where email_hmac is not null
    union all
    select email_hmac, platform_customer_id from orders
    where email_hmac is not null and platform_customer_id is not null
  ) x
  group by 1
),

attribution as (
  select o.source, o.order_id, f.field, f.value
  from orders o
  cross join lateral (
    values ('utm_medium', o.utm_medium), ('utm_source', o.utm_source),
           ('referrer', o.referrer), ('discount_code', o.discount_code)
  ) f (field, value)
  where f.value is not null
),

channel as (
  select distinct on (a.source, a.order_id) a.source, a.order_id, r.channel
  from attribution a
  join {{ ref('channel_rules') }} r
    on r.field = a.field
   and (
        (r.match_type = 'exact' and a.value = lower(r.pattern))
     or (r.match_type = 'prefix' and starts_with(a.value, lower(r.pattern)))
     or (r.match_type = 'contains' and position(lower(r.pattern) in a.value) > 0)
   )
  order by a.source, a.order_id, r.priority
),

enriched as (
  select
    o.*,
    {{ to_local('o.order_ts_utc') }}                    as order_ts_local,
    ({{ to_local('o.order_ts_utc') }})::date            as order_date_local,
    case
      when o.currency is null or o.currency = {{ reporting_currency() }} then 1.0
      else (
        select x.rate
        from {{ source('raw', 'fx_rates') }} x
        where x.base = o.currency
          and x.quote = {{ reporting_currency() }}
          and x.date <= ({{ to_local('o.order_ts_utc') }})::date
        order by x.date desc
        limit 1
      )
    end                                                 as fx_rate,
    case
      when o.platform_customer_id is not null then 'c:' || o.platform_customer_id
      when eo.owner_id is not null then 'c:' || eo.owner_id
      when o.email_hmac is not null then 'e:' || o.email_hmac
    end                                                 as customer_key,
    case
      when o.platform_customer_id is not null then 'platform_id'
      when eo.owner_id is not null then 'email_merged'
      when o.email_hmac is not null then 'email_only'
      else 'none'
    end                                                 as identity_method,
    coalesce(it.gross_amount, 0)                        as gross_amount,
    coalesce(rt.refunded_amount, 0)                     as refunded_amount
  from orders o
  left join email_owner eo on eo.email_hmac = o.email_hmac and o.platform_customer_id is null
  left join item_totals it on it.source = o.source and it.order_id = o.order_id
  left join refund_totals rt on rt.source = o.source and rt.order_id = o.order_id
),

valued as (
  select
    e.*,
    e.gross_amount * e.fx_rate                          as gross_revenue,
    e.refunded_amount * e.fx_rate                       as refunded_revenue,
    (e.gross_amount - e.refunded_amount) * e.fx_rate    as net_revenue
  from enriched e
)

select
  v.source,
  v.order_id,
  v.customer_key,
  v.identity_method,
  v.platform_customer_id,
  v.email_hmac,
  v.order_ts_utc,
  v.order_ts_local,
  v.order_date_local,
  v.currency,
  v.fx_rate,
  v.status,
  v.is_test,
  v.gross_revenue,
  v.refunded_revenue,
  v.net_revenue,
  case
    when v.order_date_local >= {{ data_cutoff() }} then 'after_cutoff'
    when v.is_test then 'test_order'
    when v.status not in {{ qualifying_status_list() }} then 'status'
    when v.fx_rate is null then 'missing_fx_rate'
    when v.net_revenue <= 0 then 'fully_refunded_or_zero'
  end                                                   as exclusion_reason,
  coalesce(
    v.order_date_local < {{ data_cutoff() }}
    and not v.is_test
    and v.status in {{ qualifying_status_list() }}
    and v.net_revenue > 0,
    false
  )                                                     as is_qualifying,
  pl.primary_category,
  pl.primary_product_id,
  pl.primary_product_name,
  ch.channel                                            as acquisition_channel,
  v.country
from valued v
left join primary_line pl on pl.source = v.source and pl.order_id = v.order_id
left join channel ch on ch.source = v.source and ch.order_id = v.order_id
