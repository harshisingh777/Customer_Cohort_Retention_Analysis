-- Invariant: no rate above 1 (active or repeaters never exceed the cohort).
select 'retention_monthly' as mart, cohort_month::text as cohort, period_number
from {{ ref('mart_cohort_retention_monthly') }}
where active_customers > cohort_customers or cum_repeat_customers > cohort_customers

union all

select 'retention_weekly', cohort_week::text, period_number
from {{ ref('mart_cohort_retention_weekly') }}
where active_customers > cohort_customers or cum_repeat_customers > cohort_customers

union all

select 'first_product_repeat', item_id, null
from {{ ref('mart_first_product_repeat') }}
where repeat_90d > eligible_90d or eligible_90d > first_buyers

union all

select 'ltv_cohort', cohort_month::text, null
from {{ ref('mart_ltv_cohort') }}
where repeat_90d > repeat_eligible_90d or eligible_365d > customers

union all

select 'lapse_monthly', month_end::text, null
from {{ ref('mart_lapse_monthly') }}
where lapsed_customers > base_customers
