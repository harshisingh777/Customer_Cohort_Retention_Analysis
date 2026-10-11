-- Invariant: marts only ever sum qualifying orders, which have net revenue > 0.
select 'cohort_revenue_monthly' as mart, net_revenue from {{ ref('mart_cohort_revenue_monthly') }} where net_revenue < 0
union all
select 'cohort_revenue_weekly', net_revenue from {{ ref('mart_cohort_revenue_weekly') }} where net_revenue < 0
union all
select 'customer_state', net_revenue from {{ ref('mart_customer_state') }} where net_revenue <= 0
union all
select 'channel_month', net_revenue from {{ ref('mart_channel_month') }} where net_revenue < 0
