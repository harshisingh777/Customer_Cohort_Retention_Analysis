{#
  Cohort x dimensions x period cells, ONLY for observable periods (spec §5.4).

  A missing row means "not observable yet". A row with 0 means "observed, nobody bought".
  The current, incomplete period is excluded both as a cohort and as an activity period
  (generate_series with a negative upper bound returns nothing).

  Columns: cohort, dims, period_number, cohort_customers, active_customers,
           cum_repeat_customers (had a 2nd qualifying order by the end of period N),
           net_revenue (all qualifying revenue of the cohort's customers in period N).
#}
{% macro cohort_cells(grain) %}
{%- set cohort_col = 'cohort_month' if grain == 'month' else 'cohort_week' -%}
{%- set activity_model = 'int_customer_activity_monthly' if grain == 'month' else 'int_customer_activity_weekly' -%}
{%- set activity_col = 'activity_month' if grain == 'month' else 'activity_week' -%}

with acq as (
  select customer_key, {{ cohort_col }} as cohort, acquisition_channel, country, first_category
  from {{ ref('int_customer_acquisition') }}
),

act as (
  select customer_key, {{ activity_col }} as activity
  from {{ ref(activity_model) }}
),

orders as (
  select customer_key, date_trunc('{{ grain }}', order_ts_local)::date as bucket, net_revenue, order_seq
  from {{ ref('int_orders') }}
),

bounds as (
  select {{ last_complete(grain) }} as last_complete
),

cohort_sizes as (
  select cohort, acquisition_channel, country, first_category, count(*) as cohort_customers
  from acq
  group by 1, 2, 3, 4
),

activity as (
  select
    a.cohort, a.acquisition_channel, a.country, a.first_category,
    {{ periods_between(grain, 'a.cohort', 'x.activity') }} as period_number,
    count(*) as active_customers           -- activity is already distinct per customer-period
  from acq a
  join act x using (customer_key)
  group by 1, 2, 3, 4, 5
),

revenue as (
  select
    a.cohort, a.acquisition_channel, a.country, a.first_category,
    {{ periods_between(grain, 'a.cohort', 'o.bucket') }} as period_number,
    sum(o.net_revenue)                                   as net_revenue,
    count(*) filter (where o.order_seq = 2)              as second_orders
  from acq a
  join orders o using (customer_key)
  group by 1, 2, 3, 4, 5
),

grid as (
  -- every observable (cohort, period) cell, so observed zeros exist as rows
  select c.*, p.period_number
  from cohort_sizes c
  cross join bounds b
  cross join lateral generate_series(
    0,
    {{ periods_between(grain, 'c.cohort', 'b.last_complete') }}
  ) as p(period_number)
)

select
  g.cohort                                as {{ cohort_col }},
  g.acquisition_channel,
  g.country,
  g.first_category,
  g.period_number,
  g.cohort_customers,
  coalesce(a.active_customers, 0)         as active_customers,
  sum(coalesce(r.second_orders, 0)) over (
    partition by g.cohort, g.acquisition_channel, g.country, g.first_category
    order by g.period_number
    rows between unbounded preceding and current row
  )::int                                  as cum_repeat_customers,
  coalesce(r.net_revenue, 0)::numeric(16, 2) as net_revenue
from grid g
left join activity a
  using (cohort, acquisition_channel, country, first_category, period_number)
left join revenue r
  using (cohort, acquisition_channel, country, first_category, period_number)
{% endmacro %}
