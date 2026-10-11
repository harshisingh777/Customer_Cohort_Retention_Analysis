-- The store's own lapse threshold: 90th percentile of gaps between consecutive orders for
-- customers with 2+ orders, clamped to 60-365 days. An admin override replaces it.
with gaps as (
  select (next_order_ts_local::date - order_ts_local::date) as gap_days
  from {{ ref('int_orders') }}
  where next_order_ts_local is not null
),

stats as (
  select
    percentile_cont(0.9) within group (order by gap_days) as p90_gap_days,
    percentile_cont(0.5) within group (order by gap_days) as median_gap_days,
    count(*)                                              as gap_count
  from gaps
)

select
  p90_gap_days,
  median_gap_days,
  gap_count,
  least(365, greatest(60, round(coalesce(p90_gap_days, 365))))::int as derived_threshold_days,
  {{ var('lapse_threshold_override') if var('lapse_threshold_override') else 'null' }}::int
                                                                    as override_threshold_days,
  coalesce(
    {{ var('lapse_threshold_override') if var('lapse_threshold_override') else 'null' }}::int,
    least(365, greatest(60, round(coalesce(p90_gap_days, 365))))::int
  )                                                                 as threshold_days
from stats
