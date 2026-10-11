{{ config(schema='pii', indexes=[{'columns': ['customer_key'], 'unique': True}]) }}

-- The admin-only path to customer emails. Built into pii_build and swapped with the marts.
-- api_ro has no grant on pii; it reads through ops.customer_contacts(), which masks for viewers.
with order_emails as (
  select s.customer_key, o.email, o.order_ts_utc
  from ({{ normalized_orders() }}) o
  join {{ ref('stg_orders') }} s on s.source = o.source and s.order_id = o.order_id
  where o.email is not null and s.customer_key is not null
),

registered as (
  select 'c:' || platform_customer_id as customer_key, email
  from ({{ normalized_customers() }}) c
  where email is not null
),

ranked as (
  select customer_key, email, 1 as preference, null::timestamptz as seen_at from registered
  union all
  select customer_key, email, 2, order_ts_utc from order_emails
)

select distinct on (customer_key) customer_key, email
from ranked
order by customer_key asc, preference asc, seen_at desc nulls last
