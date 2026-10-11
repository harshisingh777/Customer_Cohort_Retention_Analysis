{#
  HMAC-SHA256 of the normalised email, keyed by PII_KEY. A plain hash of an email is
  reversible with a lookup table; a keyed one is not without the key.
  The key arrives as the session setting retention.pii_key (set via PGOPTIONS by the worker),
  so it is never written into compiled SQL or query logs.
#}
{% macro hmac_email(col) -%}
  case
    when nullif(trim({{ col }}), '') is null then null
    else encode(hmac(lower(trim({{ col }})), current_setting('retention.pii_key'), 'sha256'), 'hex')
  end
{%- endmacro %}
