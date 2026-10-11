{% macro qualifying_status_list() -%}
  ({%- for s in var('qualifying_statuses') -%}'{{ s | lower | replace("'", "''") }}'{%- if not loop.last -%}, {% endif -%}{%- endfor -%})
{%- endmacro %}

{% macro reporting_currency() -%}
  '{{ var("reporting_currency") | upper }}'
{%- endmacro %}

{# Named RFM segments as regions of the Recency x Frequency grid (both scored 1-5). #}
{% macro rfm_segment(r, f) -%}
  case
    when {{ r }} >= 4 and {{ f }} >= 4 then 'Champions'
    when {{ r }} >= 4 and {{ f }} = 3 then 'Loyal'
    when {{ r }} = 3 and {{ f }} >= 3 then 'Loyal'
    when {{ r }} >= 4 and {{ f }} = 2 then 'Potential loyalists'
    when {{ r }} >= 4 and {{ f }} = 1 then 'New customers'
    when {{ r }} = 3 and {{ f }} <= 2 then 'Needs attention'
    when {{ r }} <= 2 and {{ f }} >= 4 then 'Can''t lose them'
    when {{ r }} <= 2 and {{ f }} >= 2 then 'At risk'
    else 'Lost'
  end
{%- endmacro %}
