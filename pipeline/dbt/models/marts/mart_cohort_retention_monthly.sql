{{ config(
    materialized = 'table',
    indexes = [
      {'columns': ['cohort_month', 'period_number']},
      {'columns': ['acquisition_channel', 'country', 'first_category']}
    ]
) }}

-- One row per (cohort_month, acquisition_channel, country, first_category, period_number),
-- only for observable periods. See macros/cohort_cells.sql.
{{ cohort_cells('month') }}
