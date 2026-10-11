{{ config(
    materialized = 'table',
    indexes = [
      {'columns': ['cohort_week', 'period_number']},
      {'columns': ['acquisition_channel', 'country', 'first_category']}
    ]
) }}

{{ cohort_cells('week') }}
