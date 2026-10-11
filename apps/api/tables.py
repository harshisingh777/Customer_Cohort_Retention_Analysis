"""SQLAlchemy Core table definitions for what the API reads. Every query is built from these
with bound parameters; there is no string-built SQL in the API."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

md = MetaData()
A = "analytics"


def _dims() -> list[Column]:
    return [
        Column("acquisition_channel", Text),
        Column("country", Text),
        Column("first_category", Text),
    ]


retention_monthly = Table(
    "mart_cohort_retention_monthly",
    md,
    Column("cohort_month", Date),
    *_dims(),
    Column("period_number", Integer),
    Column("cohort_customers", BigInteger),
    Column("active_customers", BigInteger),
    Column("cum_repeat_customers", BigInteger),
    Column("net_revenue", Numeric),
    schema=A,
)

retention_weekly = Table(
    "mart_cohort_retention_weekly",
    md,
    Column("cohort_week", Date),
    *_dims(),
    Column("period_number", Integer),
    Column("cohort_customers", BigInteger),
    Column("active_customers", BigInteger),
    Column("cum_repeat_customers", BigInteger),
    Column("net_revenue", Numeric),
    schema=A,
)

second_order_days = Table(
    "mart_second_order_days",
    md,
    Column("cohort_month", Date),
    *_dims(),
    Column("days_to_second", Integer),
    Column("customers", BigInteger),
    schema=A,
)

first_product_repeat = Table(
    "mart_first_product_repeat",
    md,
    Column("level", Text),
    Column("item_id", Text),
    Column("item_label", Text),
    Column("cohort_month", Date),
    *_dims(),
    Column("first_buyers", BigInteger),
    Column("eligible_90d", BigInteger),
    Column("repeat_90d", BigInteger),
    schema=A,
)

customer_state = Table(
    "mart_customer_state",
    md,
    Column("customer_key", Text),
    Column("cohort_month", Date),
    *_dims(),
    Column("first_product_name", Text),
    Column("first_order_date", Date),
    Column("last_order_date", Date),
    Column("orders", BigInteger),
    Column("net_revenue", Numeric),
    Column("avg_order_value", Numeric),
    Column("days_since_last", Integer),
    Column("age_days", Integer),
    Column("is_lapsed", Boolean),
    Column("ltv_90d", Numeric),
    Column("ltv_180d", Numeric),
    Column("ltv_365d", Numeric),
    Column("rfm_r", Integer),
    Column("rfm_f", Integer),
    Column("rfm_m", Integer),
    Column("rfm_segment", Text),
    schema=A,
)

customer_clv = Table(
    "mart_customer_clv",
    md,
    Column("customer_key", Text),
    Column("p_alive", Numeric),
    Column("pred_orders_12m", Numeric),
    Column("pred_ltv_12m_p10", Numeric),
    Column("pred_ltv_12m_p50", Numeric),
    Column("pred_ltv_12m_p90", Numeric),
    Column("model_version", Text),
    Column("fitted_at", DateTime(timezone=True)),
    Column("holdout_mape", Numeric),
    schema=A,
)

clv_model = Table(
    "mart_clv_model",
    md,
    Column("model_version", Text),
    Column("fitted_at", DateTime(timezone=True)),
    Column("cutoff_date", Date),
    Column("method", Text),
    Column("n_customers", Integer),
    Column("holdout_days", Integer),
    Column("holdout_mape", Numeric),
    Column("cohort_month", Date),
    Column("customers", Integer),
    Column("predicted_revenue", Numeric),
    Column("actual_revenue", Numeric),
    schema=A,
)

clv_group_draws = Table(
    "mart_clv_group_draws",
    md,
    Column("acquisition_channel", Text),
    Column("cohort_month", Date),
    Column("customers", BigInteger),
    Column("draw_sums", ARRAY(Float)),
    schema=A,
)

rfm_cells = Table(
    "mart_rfm_cells",
    md,
    Column("rfm_r", Integer),
    Column("rfm_f", Integer),
    Column("rfm_segment", Text),
    Column("cohort_month", Date),
    *_dims(),
    Column("customers", BigInteger),
    Column("net_revenue", Numeric),
    Column("lapsed_customers", BigInteger),
    schema=A,
)

ltv_cohort = Table(
    "mart_ltv_cohort",
    md,
    Column("cohort_month", Date),
    *_dims(),
    Column("customers", BigInteger),
    Column("eligible_90d", BigInteger),
    Column("ltv_90d_sum", Numeric),
    Column("eligible_180d", BigInteger),
    Column("ltv_180d_sum", Numeric),
    Column("eligible_365d", BigInteger),
    Column("ltv_365d_sum", Numeric),
    Column("repeat_eligible_90d", BigInteger),
    Column("repeat_90d", BigInteger),
    schema=A,
)

lapse_monthly = Table(
    "mart_lapse_monthly",
    md,
    Column("month_end", Date),
    *_dims(),
    Column("base_customers", BigInteger),
    Column("lapsed_customers", BigInteger),
    schema=A,
)

channel_month = Table(
    "mart_channel_month",
    md,
    Column("acquisition_channel", Text),
    Column("cohort_month", Date),
    Column("period_number", Integer),
    Column("new_customers", BigInteger),
    Column("net_revenue", Numeric),
    Column("cum_net_revenue_per_customer", Numeric),
    schema=A,
)

channel_spend = Table(
    "mart_channel_spend_monthly",
    md,
    Column("channel", Text),
    Column("month", Date),
    Column("spend", Numeric),
    schema=A,
)

reconciliation = Table(
    "mart_reconciliation",
    md,
    Column("day", Date),
    Column("source_orders", BigInteger),
    Column("source_revenue", Numeric),
    Column("mart_orders", BigInteger),
    Column("mart_revenue", Numeric),
    Column("unidentified_revenue", Numeric),
    Column("delta", Numeric),
    schema=A,
)

data_quality = Table(
    "mart_data_quality",
    md,
    Column("data_through", Date),
    Column("cutoff_date", Date),
    Column("reporting_tz", Text),
    Column("reporting_currency", Text),
    Column("orders_total", BigInteger),
    Column("orders_qualifying", BigInteger),
    Column("orders_test", BigInteger),
    Column("orders_status_excluded", BigInteger),
    Column("orders_refunded_or_zero", BigInteger),
    Column("orders_missing_fx", BigInteger),
    Column("orders_after_cutoff", BigInteger),
    Column("first_order_date", Date),
    Column("last_order_date", Date),
    Column("guest_orders", BigInteger),
    Column("guest_orders_merged", BigInteger),
    Column("orders_without_identity", BigInteger),
    Column("identity_merge_rate", Numeric),
    Column("lines_total", BigInteger),
    Column("lines_product", BigInteger),
    Column("lines_uncategorized", BigInteger),
    Column("customers", BigInteger),
    Column("customers_unattributed", BigInteger),
    Column("customers_uncategorized", BigInteger),
    Column("repeat_customers", BigInteger),
    Column("lapse_threshold_days", Integer),
    Column("derived_threshold_days", Integer),
    Column("override_threshold_days", Integer),
    Column("p90_gap_days", Numeric),
    Column("gap_count", BigInteger),
    schema=A,
)

int_orders = Table(
    "int_orders",
    md,
    Column("order_id", Text),
    Column("customer_key", Text),
    Column("order_ts_local", DateTime),
    Column("order_date_local", Date),
    Column("net_revenue", Numeric),
    Column("primary_category", Text),
    Column("primary_product_name", Text),
    Column("order_seq", Integer),
    schema=A,
)

# ops ------------------------------------------------------------------------------------
settings_t = Table(
    "settings",
    md,
    Column("key", Text),
    Column("value", JSONB),
    Column("updated_at", DateTime(timezone=True)),
    Column("updated_by", Text),
    schema="ops",
)
users_t = Table(
    "users",
    md,
    Column("email", Text),
    Column("role", Text),
    Column("name", Text),
    Column("invited_by", Text),
    Column("invited_at", DateTime(timezone=True)),
    Column("last_seen_at", DateTime(timezone=True)),
    Column("disabled", Boolean),
    schema="ops",
)
jobs_t = Table(
    "jobs",
    md,
    Column("id", BigInteger),
    Column("kind", Text),
    Column("payload", JSONB),
    Column("status", Text),
    Column("scheduled_for", DateTime(timezone=True)),
    Column("attempts", Integer),
    Column("error", Text),
    Column("created_by", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    schema="ops",
)
runs_t = Table(
    "pipeline_runs",
    md,
    Column("id", BigInteger),
    Column("job_id", BigInteger),
    Column("kind", Text),
    Column("trigger", Text),
    Column("status", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("steps", JSONB),
    Column("tests", JSONB),
    Column("reconciliation", JSONB),
    Column("row_counts", JSONB),
    Column("error", Text),
    Column("data_version", Text),
    schema="ops",
)
versions_t = Table(
    "data_versions",
    md,
    Column("version", Text),
    Column("run_id", BigInteger),
    Column("data_through", Date),
    Column("published_at", DateTime(timezone=True)),
    schema="ops",
)
batches_t = Table(
    "ingest_batches",
    md,
    Column("batch_id", UUID),
    Column("source", Text),
    Column("entity", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("rows_in", Integer),
    Column("rows_upserted", Integer),
    Column("rows_dropped", Integer),
    Column("drop_reasons", JSONB),
    schema="ops",
)
audit_t = Table(
    "audit_log",
    md,
    Column("id", BigInteger),
    Column("at", DateTime(timezone=True)),
    Column("actor", Text),
    Column("action", Text),
    Column("detail", JSONB),
    schema="ops",
)
exports_t = Table(
    "exports",
    md,
    Column("id", UUID(as_uuid=False)),
    Column("owner", Text),
    Column("format", Text),
    Column("view", Text),
    Column("params", JSONB),
    Column("status", Text),
    Column("job_id", BigInteger),
    Column("storage", Text),
    Column("storage_key", Text),
    Column("error", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    schema="ops",
)
export_files_t = Table(
    "export_files",
    md,
    Column("export_id", UUID(as_uuid=False)),
    Column("content", LargeBinary),
    Column("content_type", Text),
    schema="ops",
)
