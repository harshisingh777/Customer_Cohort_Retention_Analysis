"""Response and request models. They drive the OpenAPI schema the TypeScript client is
generated from, so every field the UI reads is typed here."""

from __future__ import annotations

import datetime as dt
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class Meta(BaseModel):
    data_version: str
    data_through: dt.date
    timezone: str
    currency: str
    filters: dict[str, Any] = {}
    metrics: list[str] = []


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


# Findings -------------------------------------------------------------------------------
class Finding(BaseModel):
    id: str
    kind: Literal["cohort", "timing", "first_purchase"]
    text: str
    href: str
    effect: float
    metric_ids: list[str]


# Cohorts --------------------------------------------------------------------------------
class CohortRow(BaseModel):
    cohort: str
    size: int
    active: list[float]
    rate: list[float | None]
    low: list[float | None]
    high: list[float | None]


class CohortTable(BaseModel):
    granularity: Literal["month", "week"]
    measure: Literal["customers", "revenue", "cumulative"]
    periods: list[int]
    cohorts: list[CohortRow]
    findings: list[Finding] = []


class CurveSeries(BaseModel):
    cohort: str
    size: int
    values: list[float | None]


class Curves(BaseModel):
    granularity: Literal["month", "week"]
    measure: Literal["customers", "revenue", "cumulative"]
    periods: list[int]
    series: list[CurveSeries]
    median: list[float | None] = Field(description="Median of the last six cohorts at each period")
    median_of: list[str]


# Repeat ---------------------------------------------------------------------------------
class HistBin(BaseModel):
    start: int
    end: int | None = Field(description="Inclusive; null for the open-ended last bin")
    customers: int


class SecondOrder(BaseModel):
    bins: list[HistBin]
    median_days: int | None
    p90_days: int | None
    repeaters: int
    first_buyers: int
    share_after_90: float | None
    findings: list[Finding] = []


class FirstProductRow(BaseModel):
    item_id: str
    label: str
    first_buyers: int
    eligible: int
    repeaters: int
    rate: float | None
    low: float | None
    high: float | None
    diff_pts: float | None


class StoreRate(BaseModel):
    eligible: int
    repeaters: int
    rate: float | None


class FirstProduct(BaseModel):
    level: Literal["category", "product"]
    min_buyers: int
    store: StoreRate
    rows: list[FirstProductRow]
    hidden_small: int = Field(
        description="Items left out for having fewer than min_buyers eligible customers"
    )
    findings: list[Finding] = []


# Segments and customers -----------------------------------------------------------------
class RfmCell(BaseModel):
    r: int
    f: int
    segment: str
    customers: int
    avg_value: float | None
    lapsed: int


class RfmSegment(BaseModel):
    name: str
    customers: int
    share: float
    net_revenue: float
    avg_value: float | None


class Rfm(BaseModel):
    cells: list[RfmCell]
    segments: list[RfmSegment]
    total_customers: int


class CustomerRow(BaseModel):
    customer_key: str
    email: str | None
    cohort: str
    channel: str
    country: str
    first_category: str
    orders: int
    net_revenue: float
    last_order_date: dt.date
    days_since_last: int
    is_lapsed: bool
    is_drifting: bool | None
    segment: str
    r: int
    f: int
    m: int
    p_alive: float | None
    pred_ltv_p10: float | None
    pred_ltv_p50: float | None
    pred_ltv_p90: float | None


class CustomerPage(BaseModel):
    rows: list[CustomerRow]
    next_cursor: str | None
    total: int


class CustomerOrder(BaseModel):
    order_id: str
    date: dt.date
    net_revenue: float
    category: str | None
    product: str | None


class CustomerDetail(CustomerRow):
    first_order_date: dt.date
    avg_order_value: float
    ltv_90d: float | None
    ltv_180d: float | None
    ltv_365d: float | None
    first_product: str | None
    orders_timeline: list[CustomerOrder]


# Channels -------------------------------------------------------------------------------
class Coverage(BaseModel):
    new_customers: int
    attributed: int
    share: float | None


class ChannelRow(BaseModel):
    channel: str
    new_customers: int
    spend: float | None
    cac: float | None
    ltv_365: float | None
    ltv_365_eligible: int
    ltv_basis: Literal["historical", "predicted"] | None
    pred_ltv_p10: float | None
    pred_ltv_p50: float | None
    pred_ltv_p90: float | None
    ltv_cac: float | None
    payback_month: int | None


class Channels(BaseModel):
    coverage: Coverage
    has_spend: bool
    gross_margin: float | None
    clv_visible: bool
    clv_hidden_reason: str | None
    rows: list[ChannelRow]


# Summary --------------------------------------------------------------------------------
class VitalPoint(BaseModel):
    label: str
    value: float | None
    n: int


class Vital(BaseModel):
    id: str
    metric_id: str
    label: str
    kind: Literal["count", "rate", "currency"]
    current: VitalPoint | None
    previous: VitalPoint | None
    change: dict[str, Any] | None


class Summary(BaseModel):
    findings: list[Finding]
    vitals: list[Vital]
    low_repeat: bool = Field(
        description="True when repeat is rare; the UI leads with timing and first-purchase findings"
    )


# Meta, metrics, settings ----------------------------------------------------------------
class RunBrief(BaseModel):
    id: int
    status: str
    trigger: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    error: str | None


class Freshness(BaseModel):
    state: Literal["fresh", "stale", "empty"]
    message: str | None
    last_run: RunBrief | None


class Dimensions(BaseModel):
    channels: list[str]
    countries: list[str]
    categories: list[str]


class DateBounds(BaseModel):
    min_month: dt.date | None
    max_month: dt.date | None
    min_week: dt.date | None
    max_week: dt.date | None


class MetaData(BaseModel):
    data_version: str | None
    data_through: dt.date | None
    published_at: dt.datetime | None
    store_name: str
    timezone: str
    currency: str
    locale: str
    freshness: Freshness
    dimensions: Dimensions
    bounds: DateBounds
    lapse_threshold_days: int | None
    has_spend: bool
    has_clv: bool
    clv_visible: bool
    gross_margin: float | None
    role: Literal["admin", "viewer"]
    email: str


class MetricDef(BaseModel):
    id: str
    label: str
    short: str | None
    definition: str
    formula: str
    model: str
    unit: str
    caveats: list[str]


class SettingsOut(BaseModel):
    store_name: str
    reporting_tz: str
    reporting_currency: str
    locale: str
    qualifying_statuses: list[str]
    lapse_threshold_days: int | None
    gross_margin: float | None
    as_of_date: dt.date | None
    refresh_time_local: str
    clv_weekday: int


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_name: str | None = None
    reporting_tz: str | None = None
    reporting_currency: str | None = None
    locale: str | None = None
    qualifying_statuses: list[str] | None = None
    lapse_threshold_days: int | None = None
    gross_margin: float | None = None
    refresh_time_local: str | None = None
    clear: list[Literal["lapse_threshold_days", "gross_margin", "as_of_date"]] = []


class SettingsSaved(BaseModel):
    settings: SettingsOut
    rebuild_job_id: int | None


class MetricsDoc(BaseModel):
    rules: dict[str, str]
    metrics: list[MetricDef]
    settings: SettingsOut
    lapse_threshold: dict[str, Any] | None


# Data health ----------------------------------------------------------------------------
class RunOut(RunBrief):
    duration_s: float | None
    steps: list[dict[str, Any]]
    tests: dict[str, Any] | None
    reconciliation: dict[str, Any] | None
    data_version: str | None


class ReconDay(BaseModel):
    day: dt.date
    source_revenue: float
    mart_revenue: float
    delta: float


class DataHealth(BaseModel):
    freshness: Freshness
    data_version: str | None
    data_through: dt.date | None
    published_at: dt.datetime | None
    runs: list[RunOut]
    reconciliation_daily: list[ReconDay]
    reconciliation: dict[str, Any] | None
    quality: dict[str, Any] | None
    ingest: list[dict[str, Any]]
    clv: dict[str, Any] | None


# Pipeline, exports, users ---------------------------------------------------------------
class RunRequested(BaseModel):
    job_id: int
    status: str
    existing: bool


class JobOut(BaseModel):
    job_id: int
    kind: str
    status: str
    attempts: int
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None
    run: RunOut | None


ExportView = Literal[
    "summary", "cohorts", "repeat", "segments", "channels", "customers", "data", "first_product"
]


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["csv", "pdf"]
    view: ExportView
    params: dict[str, str | list[str]] = {}


class ExportOut(BaseModel):
    id: str
    status: str
    view: str
    created_at: dt.datetime
    download_url: str | None
    expires_at: dt.datetime | None
    error: str | None


class UserOut(BaseModel):
    email: str
    role: Literal["admin", "viewer"]
    name: str | None
    invited_by: str | None
    invited_at: dt.datetime
    last_seen_at: dt.datetime | None
    disabled: bool


class UserInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: Literal["admin", "viewer"] = "viewer"
    name: str | None = None


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "viewer"] | None = None
    disabled: bool | None = None
