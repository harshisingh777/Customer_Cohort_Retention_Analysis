-- The raw layer. Owned by ingest; every source row keeps its full payload.
-- Idempotent: executed at the start of every ingest.

create schema if not exists raw;

create table if not exists raw.customers (
  source             text not null,
  source_id          text not null,
  payload            jsonb not null,
  source_updated_at  timestamptz not null,
  _batch_id          uuid not null,
  _ingested_at       timestamptz not null default now(),
  primary key (source, source_id)
);

create table if not exists raw.orders (like raw.customers including all);
create table if not exists raw.order_items (like raw.customers including all);
create table if not exists raw.refunds (like raw.customers including all);

create index if not exists order_items_order_idx on raw.order_items ((payload ->> 'order_id'));
create index if not exists refunds_order_idx on raw.refunds ((payload ->> 'order_id'));

create table if not exists raw.marketing_spend (
  date          date not null,
  channel       text not null,
  spend_amount  numeric(14, 2) not null check (spend_amount >= 0),
  currency      text not null default 'GBP',
  _ingested_at  timestamptz not null default now(),
  primary key (date, channel)
);

create table if not exists raw.fx_rates (
  date   date not null,
  base   text not null,
  quote  text not null,
  rate   numeric(18, 8) not null check (rate > 0),
  primary key (date, base, quote)
);

-- Outputs of the weekly CLV fit. They are inputs to the marts, so they live with the other inputs.
create table if not exists raw.clv_runs (
  model_version   text primary key,
  fitted_at       timestamptz not null default now(),
  cutoff_date     date not null,
  method          text not null,
  n_customers     int not null,
  holdout_days    int not null,
  holdout_mape    numeric,
  diagnostics     jsonb not null default '{}'::jsonb
);

create table if not exists raw.clv_predictions (
  model_version    text not null references raw.clv_runs(model_version) on delete cascade,
  customer_key     text not null,
  p_alive          numeric not null,
  pred_orders_12m  numeric not null,
  pred_ltv_12m_p10 numeric not null,
  pred_ltv_12m_p50 numeric not null,
  pred_ltv_12m_p90 numeric not null,
  primary key (model_version, customer_key)
);

create table if not exists raw.clv_holdout (
  model_version     text not null references raw.clv_runs(model_version) on delete cascade,
  cohort_month      date not null,
  customers         int not null,
  predicted_revenue numeric not null,
  actual_revenue    numeric not null,
  primary key (model_version, cohort_month)
);

-- Sum of expected 12-month value per posterior draw, per acquisition cell: additive, so group
-- averages keep their uncertainty under any date filter.
create table if not exists raw.clv_group_draws (
  model_version        text not null references raw.clv_runs(model_version) on delete cascade,
  acquisition_channel  text not null,
  cohort_month         date not null,
  customers            int not null,
  draw_sums            float8[] not null,
  primary key (model_version, acquisition_channel, cohort_month)
);
