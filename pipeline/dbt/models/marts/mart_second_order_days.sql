{{ config(indexes=[{'columns': ['cohort_month']}, {'columns': ['acquisition_channel', 'country', 'first_category']}]) }}

-- Additive histogram of days to second order. The API sums counts under any filter and reads
-- the median and 90th percentile off the cumulative distribution.
select
  cohort_month,
  acquisition_channel,
  country,
  first_category,
  days_to_second,
  count(*) as customers
from {{ ref('mart_second_order') }}
where days_to_second is not null
group by 1, 2, 3, 4, 5
