-- Revenue and customer counts must survive every layer without fan-out or loss.
with bounds as (
  select {{ last_complete('month') }} as last_complete
),

expected_cohort_revenue as (
  -- revenue of observable cells: cohort and order month both complete
  select coalesce(sum(o.net_revenue), 0) as v
  from {{ ref('int_orders') }} o
  join {{ ref('int_customer_acquisition') }} a using (customer_key)
  cross join bounds b
  where a.cohort_month <= b.last_complete
    and date_trunc('month', o.order_ts_local)::date <= b.last_complete
),

checks as (
  select 'customer_state_revenue' as check_name,
         (select sum(net_revenue) from {{ ref('mart_customer_state') }}) as actual,
         (select sum(net_revenue) from {{ ref('int_orders') }}) as expected
  union all
  select 'cohort_revenue_monthly',
         (select coalesce(sum(net_revenue), 0) from {{ ref('mart_cohort_revenue_monthly') }}),
         (select v from expected_cohort_revenue)
  union all
  select 'customers_state_vs_acquisition',
         (select count(*) from {{ ref('mart_customer_state') }}),
         (select count(*) from {{ ref('int_customer_acquisition') }})
  union all
  select 'customers_acquisition_vs_orders',
         (select count(*) from {{ ref('int_customer_acquisition') }}),
         (select count(distinct customer_key) from {{ ref('int_orders') }})
  union all
  select 'stg_orders_unique',
         (select count(*) from {{ ref('stg_orders') }}),
         (select count(*) from (select distinct source, order_id from {{ ref('stg_orders') }}) d)
)

-- Revenue: marts round to cents per row, so allow 0.01%. Counts must match exactly.
select * from checks
where abs(coalesce(actual, 0) - coalesce(expected, 0)) > case
  when check_name like '%revenue%' then greatest(0.01, abs(coalesce(expected, 0)) * 0.0001)
  else 0
end
