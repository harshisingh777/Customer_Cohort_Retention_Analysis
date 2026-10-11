{#
  Build everything into *_build schemas. The worker swaps them into place atomically after
  the audit passes (write-audit-publish). Default schema: analytics_build. A model configured
  with schema='pii' builds into pii_build.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}_build
  {%- endif -%}
{%- endmacro %}
