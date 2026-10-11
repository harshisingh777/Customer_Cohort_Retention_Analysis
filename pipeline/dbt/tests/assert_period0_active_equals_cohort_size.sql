-- Invariant: every customer is active in their own cohort period.
select 'month' as grain, cohort_month as cohort, acquisition_channel, country, first_category,
       cohort_customers, active_customers
from {{ ref('mart_cohort_retention_monthly') }}
where period_number = 0 and active_customers <> cohort_customers

union all

select 'week', cohort_week, acquisition_channel, country, first_category,
       cohort_customers, active_customers
from {{ ref('mart_cohort_retention_weekly') }}
where period_number = 0 and active_customers <> cohort_customers
