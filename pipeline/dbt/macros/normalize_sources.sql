{#
  One place per source that knows its payload shape. Everything downstream sees one typed shape.
  Switching or adding a platform rewrites these branches only.

  Branches:
    canonical    csv, online_retail_ii, olist (adapters map files into this shape)
    shopify      GraphQL Admin API nodes
    woocommerce  REST API v3 objects
#}

{% macro normalized_orders() %}
  select
    o.source,
    o.source_id                                                   as order_id,
    nullif(o.payload ->> 'customer_id', '')                       as platform_customer_id,
    nullif(lower(trim(o.payload ->> 'email')), '')                as email,
    (o.payload ->> 'created_at')::timestamptz                     as order_ts_utc,
    upper(o.payload ->> 'currency')                               as currency,
    lower(o.payload ->> 'status')                                 as status,
    coalesce((o.payload ->> 'test')::boolean, false)              as is_test,
    nullif(o.payload ->> 'country', '')                           as country,
    lower(nullif(o.payload ->> 'utm_source', ''))                 as utm_source,
    lower(nullif(o.payload ->> 'utm_medium', ''))                 as utm_medium,
    lower(nullif(o.payload ->> 'referrer', ''))                   as referrer,
    lower(nullif(o.payload -> 'discount_codes' ->> 0, ''))        as discount_code,
    o.source_updated_at
  from {{ source('raw', 'orders') }} o
  where o.source not in ('shopify', 'woocommerce')

  union all

  select
    o.source,
    o.source_id,
    nullif(o.payload -> 'customer' ->> 'id', ''),
    nullif(lower(trim(coalesce(o.payload -> 'customer' ->> 'email', o.payload ->> 'email'))), ''),
    (o.payload ->> 'createdAt')::timestamptz,
    upper(o.payload ->> 'currencyCode'),
    case
      when o.payload ->> 'cancelledAt' is not null then 'cancelled'
      else lower(o.payload ->> 'displayFinancialStatus')
    end,
    coalesce((o.payload ->> 'test')::boolean, false),
    coalesce(o.payload -> 'shippingAddress' ->> 'countryCodeV2', o.payload -> 'billingAddress' ->> 'countryCodeV2'),
    lower(o.payload #>> '{customerJourneySummary,firstVisit,utmParameters,source}'),
    lower(o.payload #>> '{customerJourneySummary,firstVisit,utmParameters,medium}'),
    lower(o.payload #>> '{customerJourneySummary,firstVisit,referrerUrl}'),
    lower(o.payload -> 'discountCodes' ->> 0),
    o.source_updated_at
  from {{ source('raw', 'orders') }} o
  where o.source = 'shopify'

  union all

  select
    o.source,
    o.source_id,
    nullif(nullif(o.payload ->> 'customer_id', '0'), ''),
    nullif(lower(trim(o.payload -> 'billing' ->> 'email')), ''),
    ((o.payload ->> 'date_created_gmt') || '+00')::timestamptz,
    upper(o.payload ->> 'currency'),
    lower(o.payload ->> 'status'),
    false,
    coalesce(nullif(o.payload -> 'shipping' ->> 'country', ''), nullif(o.payload -> 'billing' ->> 'country', '')),
    (select lower(m ->> 'value') from jsonb_array_elements(coalesce(o.payload -> 'meta_data', '[]'::jsonb)) m
      where m ->> 'key' = '_wc_order_attribution_utm_source' limit 1),
    (select lower(m ->> 'value') from jsonb_array_elements(coalesce(o.payload -> 'meta_data', '[]'::jsonb)) m
      where m ->> 'key' = '_wc_order_attribution_utm_medium' limit 1),
    (select lower(m ->> 'value') from jsonb_array_elements(coalesce(o.payload -> 'meta_data', '[]'::jsonb)) m
      where m ->> 'key' = '_wc_order_attribution_referrer' limit 1),
    lower(o.payload -> 'coupon_lines' -> 0 ->> 'code'),
    o.source_updated_at
  from {{ source('raw', 'orders') }} o
  where o.source = 'woocommerce'
{% endmacro %}


{% macro normalized_order_items() %}
  select
    i.source,
    i.source_id                                         as line_id,
    i.payload ->> 'order_id'                            as order_id,
    nullif(i.payload ->> 'sku', '')                     as sku,
    nullif(i.payload ->> 'product_name', '')            as product_name,
    nullif(i.payload ->> 'category', '')                as category,
    (i.payload ->> 'quantity')::numeric                 as quantity,
    (i.payload ->> 'unit_price')::numeric               as unit_price,
    upper(i.payload ->> 'currency')                     as currency,
    coalesce(lower(i.payload ->> 'line_type'), 'product') as line_type
  from {{ source('raw', 'order_items') }} i
  where i.source not in ('shopify', 'woocommerce')

  union all

  select
    i.source,
    i.source_id,
    i.payload ->> 'order_id',
    nullif(i.payload ->> 'sku', ''),
    i.payload ->> 'name',
    nullif(i.payload #>> '{product,productType}', ''),
    (i.payload ->> 'quantity')::numeric,
    coalesce(
      (i.payload #>> '{discountedUnitPriceAfterAllDiscountsSet,shopMoney,amount}')::numeric,
      (i.payload #>> '{originalUnitPriceSet,shopMoney,amount}')::numeric
    ),
    upper(coalesce(
      i.payload #>> '{discountedUnitPriceAfterAllDiscountsSet,shopMoney,currencyCode}',
      i.payload #>> '{originalUnitPriceSet,shopMoney,currencyCode}'
    )),
    'product'
  from {{ source('raw', 'order_items') }} i
  where i.source = 'shopify'

  union all

  select
    i.source,
    i.source_id,
    i.payload ->> 'order_id',
    nullif(i.payload ->> 'sku', ''),
    i.payload ->> 'name',
    null,
    (i.payload ->> 'quantity')::numeric,
    -- `total` is the line after discounts; unit price derived from it.
    (i.payload ->> 'total')::numeric / nullif((i.payload ->> 'quantity')::numeric, 0),
    upper(i.payload ->> 'currency'),
    'product'
  from {{ source('raw', 'order_items') }} i
  where i.source = 'woocommerce'
{% endmacro %}


{% macro normalized_refunds() %}
  select
    r.source,
    r.source_id                                   as refund_id,
    r.payload ->> 'order_id'                      as order_id,
    abs((r.payload ->> 'amount')::numeric)        as amount,
    upper(r.payload ->> 'currency')               as currency,
    (r.payload ->> 'created_at')::timestamptz     as refunded_at_utc,
    nullif(r.payload ->> 'sku', '')               as sku
  from {{ source('raw', 'refunds') }} r
  where r.source not in ('shopify', 'woocommerce')

  union all

  select
    r.source,
    r.source_id,
    r.payload ->> 'order_id',
    abs((r.payload #>> '{totalRefundedSet,shopMoney,amount}')::numeric),
    upper(r.payload #>> '{totalRefundedSet,shopMoney,currencyCode}'),
    (r.payload ->> 'createdAt')::timestamptz,
    null
  from {{ source('raw', 'refunds') }} r
  where r.source = 'shopify'

  union all

  select
    r.source,
    r.source_id,
    r.payload ->> 'order_id',
    abs((r.payload ->> 'amount')::numeric),
    upper(r.payload ->> 'currency'),
    ((r.payload ->> 'date_created_gmt') || '+00')::timestamptz,
    null
  from {{ source('raw', 'refunds') }} r
  where r.source = 'woocommerce'
{% endmacro %}


{% macro normalized_customers() %}
  select
    c.source,
    c.source_id                                         as platform_customer_id,
    nullif(lower(trim(c.payload ->> 'email')), '')      as email,
    nullif(c.payload ->> 'country', '')                 as country,
    (c.payload ->> 'created_at')::timestamptz           as created_at_utc
  from {{ source('raw', 'customers') }} c
  where c.source not in ('shopify', 'woocommerce')

  union all

  select c.source, c.source_id, nullif(lower(trim(c.payload ->> 'email')), ''), null,
         (c.payload ->> 'createdAt')::timestamptz
  from {{ source('raw', 'customers') }} c
  where c.source = 'shopify'

  union all

  select c.source, c.source_id, nullif(lower(trim(c.payload ->> 'email')), ''),
         nullif(c.payload -> 'billing' ->> 'country', ''),
         ((c.payload ->> 'date_created_gmt') || '+00')::timestamptz
  from {{ source('raw', 'customers') }} c
  where c.source = 'woocommerce'
{% endmacro %}
