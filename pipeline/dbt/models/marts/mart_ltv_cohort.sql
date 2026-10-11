{{ config(indexes=[{'columns': ['cohort_month']}, {'columns': ['acquisition_channel', 'country', 'first_category']}]) }}

-- Historical LTV at fixed ages and repeat-within-90-days, per acquisition cell. Only customers
-- old enough for each window count towards it, so cohorts are comparable.
select
  s.cohort_month,
  s.acquisition_channel,
  s.country,
  s.first_category,
  count(*)                                                as customers,
  count(*) filter (where s.ltv_90d is not null)           as eligible_90d,
  coalesce(sum(s.ltv_90d), 0)::numeric(16, 2)             as ltv_90d_sum,
  count(*) filter (where s.ltv_180d is not null)          as eligible_180d,
  coalesce(sum(s.ltv_180d), 0)::numeric(16, 2)            as ltv_180d_sum,
  count(*) filter (where s.ltv_365d is not null)          as eligible_365d,
  coalesce(sum(s.ltv_365d), 0)::numeric(16, 2)            as ltv_365d_sum,
  count(*) filter (where s.age_days >= 90)                as repeat_eligible_90d,
  count(*) filter (
    where s.age_days >= 90 and so.days_to_second is not null and so.days_to_second < 90
  )                                                       as repeat_90d
from {{ ref('mart_customer_state') }} s
join {{ ref('mart_second_order') }} so using (customer_key)
group by 1, 2, 3, 4
