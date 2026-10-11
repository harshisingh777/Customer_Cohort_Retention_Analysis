{{ config(indexes=[{'columns': ['email_hmac']}, {'columns': ['platform_customer_id']}]) }}

-- Raw email is not carried past this model: only its keyed hash.
select
  c.source,
  c.platform_customer_id,
  {{ hmac_email('c.email') }}  as email_hmac,
  c.country,
  c.created_at_utc
from ({{ normalized_customers() }}) c
