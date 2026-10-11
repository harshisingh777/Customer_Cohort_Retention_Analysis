{# The first day NOT in the data, in the reporting timezone. #}
{% macro data_cutoff() -%}
  {%- if var('as_of_date') -%}
    date '{{ var("as_of_date") }}'
  {%- else -%}
    (now() at time zone '{{ var("reporting_tz") }}')::date
  {%- endif -%}
{%- endmacro %}

{# "Now" in the reporting timezone, pinned to the cutoff for static datasets. #}
{% macro local_now() -%}
  ({{ data_cutoff() }})::timestamp
{%- endmacro %}

{% macro to_local(ts_utc) -%}
  ({{ ts_utc }} at time zone '{{ var("reporting_tz") }}')
{%- endmacro %}

{# Last fully completed month / week before the cutoff. #}
{% macro last_complete(grain) -%}
  {%- if grain == 'month' -%}
    (date_trunc('month', {{ local_now() }}) - interval '1 month')::date
  {%- else -%}
    (date_trunc('week', {{ local_now() }}) - interval '7 days')::date
  {%- endif -%}
{%- endmacro %}

{# Whole periods from a to b. Plain Postgres; dbt.datediff(a, b, 'month') is the portable form. #}
{% macro periods_between(grain, a, b) -%}
  {%- if grain == 'month' -%}
    ((extract(year from {{ b }}) - extract(year from {{ a }})) * 12
     + (extract(month from {{ b }}) - extract(month from {{ a }})))::int
  {%- else -%}
    (({{ b }}::date - {{ a }}::date) / 7)::int
  {%- endif -%}
{%- endmacro %}
