{{ config(indexes=[{'columns': ['customer_key'], 'unique': True}]) }}

-- Latest BG/NBD + Gamma-Gamma predictions (written weekly by pipeline/clv), restricted to
-- customers present in this build. Empty until the first fit.
with latest as (
  select model_version, fitted_at, holdout_mape
  from {{ source('raw', 'clv_runs') }}
  order by fitted_at desc
  limit 1
)

select
  p.customer_key,
  p.p_alive::numeric(6, 4)            as p_alive,
  p.pred_orders_12m::numeric(10, 3)   as pred_orders_12m,
  p.pred_ltv_12m_p10::numeric(14, 2)  as pred_ltv_12m_p10,
  p.pred_ltv_12m_p50::numeric(14, 2)  as pred_ltv_12m_p50,
  p.pred_ltv_12m_p90::numeric(14, 2)  as pred_ltv_12m_p90,
  p.model_version,
  l.fitted_at,
  l.holdout_mape
from {{ source('raw', 'clv_predictions') }} p
join latest l using (model_version)
join {{ ref('mart_customer_state') }} using (customer_key)
