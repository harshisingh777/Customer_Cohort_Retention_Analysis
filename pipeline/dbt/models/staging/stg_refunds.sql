{{ config(indexes=[{'columns': ['source', 'order_id']}]) }}

-- Refunds of excluded lines (e.g. refunded postage) don't reduce product revenue.
with refunds as (
  select * from ({{ normalized_refunds() }}) r
),

excluded as (
  select * from {{ ref('excluded_line_codes') }}
)

select
  r.source,
  r.refund_id,
  r.order_id,
  r.amount,
  r.currency,
  r.refunded_at_utc,
  {{ to_local('r.refunded_at_utc') }} as refunded_at_local
from refunds r
where r.amount > 0
  and not exists (
    select 1
    from excluded e
    where r.sku is not null
      and (e.source = '*' or e.source = r.source)
      and (
        (e.match_type = 'exact' and r.sku = e.code)
        or (e.match_type = 'prefix' and starts_with(r.sku, e.code))
      )
  )
