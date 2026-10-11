{{ config(indexes=[{'columns': ['source', 'order_id']}]) }}

-- Product lines only. Shipping, fees and adjustments are excluded by line type and by the
-- excluded_line_codes seed. Amounts stay in the order currency; stg_orders converts.
with items as (
  select * from ({{ normalized_order_items() }}) i
),

excluded as (
  select * from {{ ref('excluded_line_codes') }}
),

keywords as (
  select * from {{ ref('category_keywords') }}
),

uncategorised_products as (
  select distinct source, sku, product_name
  from items
  where category is null and product_name is not null
),

keyword_category as (
  select distinct on (p.source, p.sku, p.product_name)
    p.source, p.sku, p.product_name, k.category
  from uncategorised_products p
  join keywords k on p.product_name ~* ('\m' || k.pattern || '\M')
  order by p.source, p.sku, p.product_name, k.priority
)

select
  i.source,
  i.line_id,
  i.order_id,
  i.sku,
  i.product_name,
  coalesce(i.category, kc.category, 'uncategorized') as category,
  i.quantity,
  i.unit_price,
  i.currency,
  i.quantity * i.unit_price                          as line_amount
from items i
left join keyword_category kc
  on kc.source = i.source
 and kc.sku is not distinct from i.sku
 and kc.product_name = i.product_name
where i.line_type = 'product'
  and i.quantity > 0
  and not exists (
    select 1
    from excluded e
    where (e.source = '*' or e.source = i.source)
      and (
        (e.match_type = 'exact' and i.sku = e.code)
        or (e.match_type = 'prefix' and starts_with(i.sku, e.code))
      )
  )
