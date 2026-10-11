# Cohort & Retention Analytics Platform: Build Specification v2.0

Supersedes the v1.0 plan (June 2026). Same goal: a deployed, authenticated dashboard that tells a non-technical e-commerce stakeholder whether the customers they acquire actually stay, and which ones. This version fixes correctness bugs in v1.0, replaces generic choices with deliberate ones, and specifies the backend down to the publish step so the dashboard is never slow, stale-without-saying-so, or half-updated.

---

## 0. What changed from v1.0, and why

| Area | v1.0 | v2.0 | Why |
|---|---|---|---|
| Cohort SQL | `datediff('month', a, b)` | `{{ dbt.datediff(...) }}` or year/month arithmetic | Postgres has no `datediff`. The core model would fail on its first run. |
| Recent cohorts | Not addressed | Censored cells are absent, not zero | Without this, every recent cohort shows 0% in later months. It is the most common lie in cohort charts. |
| Timezone | Normalize everything to UTC | Store UTC, bucket in the merchant's timezone | A US store's 9 pm order on 31 March is 1 April in UTC. Month-boundary orders land in the wrong cohort. |
| Churn | `1 − retention` | Lapse rate using a threshold derived from the store's own purchase gaps, plus P(alive) | Customers skip months and come back. "Not active in month N" is not churn. |
| Repeat purchase rate | Over a date range | Windowed: "repeat within 90 days", only for customers old enough to have had 90 days | Unwindowed, recent customers drag the rate down purely because they're new. |
| Predicted LTV | `lifetimes` or AOV × regression | BG/NBD + Gamma-Gamma via PyMC-Marketing, holdout-validated, shown as a range | `lifetimes` is unmaintained. The regression ignores dropout. A point estimate with no error bar breeds false confidence. |
| Filters | Date, channel, category, geography in any combination | Filter dimensions are customer attributes frozen at acquisition; marts are additive | Distinct-customer counts don't add across arbitrary filters, and precomputing every combination explodes. |
| Demo dataset | Olist primary | Online Retail II primary, Olist as the "low-repeat" stress case | In Olist, `customer_id` is per order. Even with `customer_unique_id`, roughly 3% of customers ever buy twice, so the heatmap is nearly empty. |
| Refresh | `dbt run` straight into tables the API reads | Write-audit-publish with an atomic schema swap | A failed or half-finished run never reaches the dashboard. |
| API speed | Query per request | Data-version keyed cache + ETags | Data changes once a day. Recomputing on every request is waste. |
| Auth | Auth.js middleware | Session in the web app, short-lived JWT verified by the API, roles enforced in the API | Next.js middleware-only auth has been bypassable (CVE-2025-29927). The API must not trust the frontend. |
| PII | `email_hash` | HMAC-SHA256 with a secret key | A plain hash of an email is reversible with a lookup table. |
| Charts | Recharts + visx | visx only; the heatmap is a semantic HTML table | One rendering model gives one visual language. Recharts v3 shipped breaking API changes. A table is keyboard-navigable, screen-reader friendly and copyable. |
| Orchestration | Dagster or cron | One idempotent pipeline job, run by a worker with a Postgres-backed queue | A Dagster daemon for one daily job on single-client hosting is ops cost with no payoff. Revisit at multi-tenant. |
| Visual design | Indigo `#2E5BFF`, Inter, slate, green/amber/red, KPI cards | §8 | That is the default SaaS dashboard. Red/green encoding fails for roughly 1 in 12 men. |
| Hosting | Render/Railway, unspecified tier | Always-on instances; nothing written to local disk | Free instances sleep (30–60 s first request) and have ephemeral disks. Both break the product. |
| Scope | Retention, churn, RFM, LTV | Adds time-to-second-order, first-product → repeat, revenue retention, payback, a Data health page, and plain-language findings | These are the numbers that actually change what a merchant does next week. |
| Timeline | 4–5 weeks part-time | ~34 focused days; 7–9 weeks part-time | v1.0 had no time for testing, hardening, or the publish layer. |

---

## 1. Product definition

**Audience.** Founder, marketing lead or ops manager of a single e-commerce store. Comfortable with spreadsheets, not with SQL.

**Primary job.** Answer "are the customers we pay to acquire coming back, and which ones?" in under a minute.

**Questions the product must answer, each in two clicks or fewer:**

1. Of the customers acquired in month X, what share bought again in each month after?
2. How long does it usually take a customer to place a second order?
3. Which first purchase (product or category) produces customers who come back?
4. Which acquisition channel produces customers worth more than they cost, and when do they pay back?
5. Which customers are drifting away right now, and how many are there?
6. Did the latest cohort behave differently from the ones before it?
7. Can I trust these numbers? (definition, freshness, and reconciliation are one click away)

**Done means:**

- Every page loads its first meaningful content in under 1.5 s on a desktop broadband connection, and every filter change shows new data in under 400 ms (warm cache).
- Every number on screen links to its definition.
- Every page shows when the data runs through.
- Totals reconcile with the source platform's own revenue report within 0.5%, and the reconciliation is visible on the Data page.
- A failed nightly run leaves yesterday's data in place and says so.

---

## 2. Scope

### v1

- Monthly and weekly cohorts by first qualifying order
- Customer retention, revenue retention, cumulative repeat curves
- Time-to-second-order distribution; first-product/category → repeat rate
- Lapse rate (churn proxy) and P(alive)-based "drifting" list
- Historical LTV at 90/180/365 days; predicted 12-month LTV as a p10–p90 range
- RFM grid with named segments and drill-down to customers
- Channel performance: CAC, LTV:CAC, payback month (only when spend data exists)
- Plain-language findings generated from deterministic templates (no LLM)
- Daily scheduled refresh, admin-triggered manual refresh
- Roles: admin, viewer. CSV export (sync), PDF export (async job)
- Methodology page generated from the same metric definitions the pipeline uses
- Data health page: runs, freshness, tests, reconciliation, identity-merge rate

### v1.1 (only after v1 is in a client's hands)

- Dark theme (tokens already support it)
- Weekly email digest of findings
- Saved views
- CSV column-mapping wizard for arbitrary platforms

### Out of scope

- Real-time or clickstream tracking. Retention is a daily-grain question.
- Campaign automation triggered by churn scores
- Multi-tenant SaaS
- Churn classifiers beyond BG/NBD. A gradient-boosted churn model needs labels this product doesn't have.

---

## 3. Architecture

```
  Shopify GraphQL / WooCommerce REST / CSV drop / public dataset
                              |
                              v
  [worker] ingest adapter ── idempotent upsert ──> raw.*            (append-friendly, JSONB payload kept)
                              |
                              v
  [worker] dbt build --target build ──> analytics_build.*           (staging -> intermediate -> marts)
                              |
                              v
  [worker] audit: dbt tests + reconciliation + row-count deltas
                   |                        |
                 pass                      fail
                   |                        |
                   v                        v
  atomic schema swap:              keep current analytics.*,
  analytics_build -> analytics     record failure, alert,
  insert ops.data_versions         Data page shows "stale since"
  NOTIFY data_published
                   |
                   v
  [api] FastAPI (read-only role) ── cache keyed by data_version ──> ETag / 304
                   |
                   v
  [web] Next.js: server-rendered first paint, TanStack Query after, URL holds all state
```

### Components

| Component | Runs on | Responsibility |
|---|---|---|
| `web` | Vercel | Rendering, auth session, minting short-lived API tokens. No data logic. |
| `api` | Always-on web service | Validates filters, reads `analytics.*`, sums additive counts, computes rates and intervals, serves findings. Read-only DB role. |
| `worker` | Always-on background service | Runs jobs from `ops.jobs`: ingest, dbt build, audit, publish, PDF export, weekly CLV fit. Internal daily schedule. |
| Postgres | Managed (Neon or equivalent) | `raw`, `analytics`, `ops` schemas. Point-in-time restore on. |
| dbt project | Inside the worker image | All business definitions. The only place a metric is defined. |
| `metrics.yml` | Repo root | Metric ids, labels, definitions, formulas, caveats. Read by dbt docs, the API (`/v1/metrics`) and the Methodology page. |

### Ownership rules

- dbt owns `analytics*` schemas. Alembic owns `ops`. Ingest owns `raw`. Nothing writes outside its schema.
- The API never defines a metric. It may filter, `SUM` additive counts, divide, and compute confidence intervals, all in one module (`api/metrics_math.py`) that is tested against dbt rollups.
- Nothing is written to the service's local disk. Not the DB, not exports, not caches that must survive a restart.

---

## 4. Technology stack

Pin exact versions in lockfiles at scaffold time. Use the current stable release of each; the versions below are the minimums the design assumes.

| Layer | Choice | Notes |
|---|---|---|
| Web framework | Next.js (App Router, ≥15), React 19, TypeScript strict | Server Components for first paint; client components only where interactive |
| Styling | Tailwind CSS v4 with CSS-variable tokens | Tokens in one `tokens.css`; Tailwind theme reads them |
| Primitives | Radix UI (via shadcn/ui source, restyled) | Take the accessibility, discard the default look: shadcn's stock zinc/radius/shadow is itself a recognizable template |
| Charts | visx + d3-scale | Heatmap is an HTML `<table>`, not a chart library component |
| Tables | TanStack Table + TanStack Virtual | Customer lists can be tens of thousands of rows |
| Data fetching | TanStack Query v5 | `placeholderData: keepPreviousData` on every filtered query |
| URL state | nuqs | Every filter lives in the URL; links are shareable and back-button safe |
| API client | Generated from OpenAPI (orval or openapi-typescript) | CI fails if the generated client drifts from the API |
| Auth | Auth.js v5 (magic link + Google), invite-only | Clerk is a fine swap if the client pays for it |
| API | FastAPI, Python 3.12+, Pydantic v2, SQLAlchemy 2 Core + asyncpg | Core, not ORM: these are read queries over marts |
| Transforms | dbt-core + dbt-postgres | dbt unit tests for cohort logic |
| CLV model | PyMC-Marketing (BG/NBD, Gamma-Gamma) | Fit weekly in the worker; results written to a mart |
| Database | PostgreSQL 16+ | One database, three schemas |
| Jobs | `ops.jobs` table + `FOR UPDATE SKIP LOCKED` | No Redis, no Celery, no Dagster for v1 |
| PDF | Playwright (Chromium) in the worker | Renders a dedicated print route |
| Tooling | uv, ruff, pyright, pytest, sqlfluff; pnpm, Biome or ESLint, Vitest, Playwright | One `justfile` drives everything |
| CI/CD | GitHub Actions | Gates listed in §11 |
| Observability | Sentry (web, api, worker), structured JSON logs, uptime check on `/readyz` | Pipeline outcome posted to a Slack or email webhook |
| Secrets | Platform env vars, `.env.example` committed, gitleaks in pre-commit and CI | `.gitignore` covers `.env*`, `*.db`, `*.duckdb`, `*.parquet` |

### Why still not Metabase

v1.0's reasoning holds: if the client is happy with a generic BI look, ship dbt + Metabase and stop at §5. The custom build earns its cost through three things a BI tool does badly: censored-cell handling in the heatmap, definitions attached to every number, and plain-language findings.

---

## 5. Data model

### 5.1 Raw layer (`raw` schema)

One table per source entity. Every row keeps the full source payload.

| Table | Key | Columns |
|---|---|---|
| `raw.customers` | `(source, source_id)` | `payload jsonb`, `source_updated_at`, `_batch_id`, `_ingested_at` |
| `raw.orders` | `(source, source_id)` | same |
| `raw.order_items` | `(source, source_id)` | same |
| `raw.refunds` | `(source, source_id)` | same |
| `raw.marketing_spend` | `(date, channel)` | `spend_amount`, `currency` (optional; CSV upload) |
| `raw.fx_rates` | `(date, base, quote)` | `rate` (daily, from a public reference-rate feed) |

Upsert rule: insert, or update only when the incoming `source_updated_at` is newer. Re-running any batch is a no-op.

### 5.2 Staging (`stg_*`)

| Model | What it does |
|---|---|
| `stg_customers` | Extracts typed columns from JSONB. `email_hmac = hmac_sha256(lower(trim(email)), $PII_KEY)`. Raw email is not carried past staging. |
| `stg_orders` | Typed columns; `order_ts_utc`; `order_ts_local = order_ts_utc at time zone $REPORTING_TZ`; converts to reporting currency at order-date FX; computes `net_revenue` after refunds; `is_qualifying`; `primary_category` (largest revenue share in the order); `acquisition_channel` from first-touch UTM/referrer/discount code where the source provides it. |
| `stg_order_items` | Typed; excludes non-product lines (shipping, fees, adjustments) via a seed list. |
| `stg_refunds` | Typed; joined into `stg_orders` net revenue. |

**Identity.** `customer_key = coalesce('c:' || platform_customer_id, 'e:' || email_hmac)`. Guest orders with the same email HMAC as a registered customer are merged into that customer. The merge rate is reported on the Data page.

**Qualifying order.** Paid, not cancelled, not a test order, and net revenue after refunds > 0. A fully refunded order does not make a customer "active" and cannot start a cohort. Partial refunds reduce revenue but keep the order qualifying. The status list is an admin setting.

### 5.3 Intermediate

**`int_customer_acquisition`** — one row per customer, attributes frozen at the first qualifying order.

```sql
with ranked as (
  select
    customer_key,
    order_id,
    order_ts_local,
    acquisition_channel,
    country,
    primary_category,
    row_number() over (
      partition by customer_key
      order by order_ts_local, order_id
    ) as order_seq
  from {{ ref('stg_orders') }}
  where is_qualifying
)
select
  customer_key,
  order_id                                       as first_order_id,
  order_ts_local                                 as first_order_ts_local,
  date_trunc('month', order_ts_local)::date      as cohort_month,
  date_trunc('week',  order_ts_local)::date      as cohort_week,
  coalesce(acquisition_channel, 'unattributed')  as acquisition_channel,
  coalesce(country, 'unknown')                   as country,
  coalesce(primary_category, 'uncategorized')    as first_category
from ranked
where order_seq = 1
```

**`int_customer_activity_monthly`** — one row per customer per month with at least one qualifying order.

```sql
select distinct
  customer_key,
  date_trunc('month', order_ts_local)::date as activity_month
from {{ ref('stg_orders') }}
where is_qualifying
```

A weekly twin exists for weekly granularity.

### 5.4 Core mart: cohort retention (corrected)

`mart_cohort_retention_monthly` — one row per (cohort_month, acquisition_channel, country, first_category, period_number), **only for observable periods**.

```sql
{{ config(
    materialized = 'table',
    indexes = [
      {'columns': ['cohort_month', 'period_number']},
      {'columns': ['acquisition_channel', 'country', 'first_category']}
    ]
) }}

with acq as (
  select * from {{ ref('int_customer_acquisition') }}
),
act as (
  select * from {{ ref('int_customer_activity_monthly') }}
),
bounds as (
  -- last fully completed month in the reporting timezone
  select (date_trunc('month', {{ local_now() }}) - interval '1 month')::date as last_complete_month
),
cohort_sizes as (
  select cohort_month, acquisition_channel, country, first_category,
         count(*) as cohort_customers
  from acq
  group by 1, 2, 3, 4
),
activity as (
  select
    a.cohort_month, a.acquisition_channel, a.country, a.first_category,
    (
      (extract(year  from x.activity_month) - extract(year  from a.cohort_month)) * 12
    + (extract(month from x.activity_month) - extract(month from a.cohort_month))
    )::int as period_number,
    count(*) as active_customers           -- activity is already distinct per customer-month
  from acq a
  join act x using (customer_key)
  group by 1, 2, 3, 4, 5
),
grid as (
  -- every observable (cohort, period) cell, so observed zeros exist as rows
  select c.*, p.period_number
  from cohort_sizes c
  cross join bounds b
  cross join lateral generate_series(
    0,
    (
      (extract(year  from b.last_complete_month) - extract(year  from c.cohort_month)) * 12
    + (extract(month from b.last_complete_month) - extract(month from c.cohort_month))
    )::int
  ) as p(period_number)
)
select
  g.cohort_month,
  g.acquisition_channel,
  g.country,
  g.first_category,
  g.period_number,
  g.cohort_customers,
  coalesce(a.active_customers, 0) as active_customers
from grid g
left join activity a
  using (cohort_month, acquisition_channel, country, first_category, period_number)
```

Properties this guarantees:

- **A missing row means "not observable yet". A row with 0 means "observed, nobody bought".** The UI renders them differently.
- The current, incomplete month is excluded both as a cohort and as an activity period (`generate_series` with a negative upper bound returns nothing).
- `period_number` arithmetic is plain Postgres. `{{ dbt.datediff("cohort_month", "activity_month", "month") }}` is an equivalent portable form.

### 5.5 Why the marts are additive

Every filter dimension (channel, country, first category) is an attribute a customer gets **once**, at acquisition. Each customer therefore sits in exactly one bucket, so for any filter combination:

```
retention_rate(cohort, N) = SUM(active_customers) / SUM(cohort_customers)
                            over the rows matching the filter
```

That makes every filtered heatmap a `SUM` over a small table: milliseconds, no combinatorial precompute. The cost is explicit: "customers who bought category X at any point" is **not** a supported filter in v1. It is a different question (behavioral, not acquisition-based) and would need an on-demand query.

### 5.6 Other marts

| Mart | Grain | Key columns |
|---|---|---|
| `mart_cohort_retention_weekly` | cohort_week × dims × period | same shape as monthly |
| `mart_cohort_revenue_monthly` | cohort_month × dims × period | `cohort_customers`, `net_revenue` |
| `mart_second_order` | customer | `first_order_ts`, `second_order_ts`, `days_to_second` (null if none), dims |
| `mart_first_product_repeat` | first product/category × dims | `first_buyers`, `eligible_90d`, `repeat_90d` |
| `mart_customer_state` | customer | `orders`, `net_revenue`, `last_order_ts`, `days_since_last`, `is_lapsed`, `ltv_90d/180d/365d`, `rfm_r/f/m`, `rfm_segment`, dims |
| `mart_customer_clv` | customer | `p_alive`, `pred_orders_12m`, `pred_ltv_12m_p10/p50/p90`, `model_version` |
| `mart_channel_month` | channel × cohort_month | `new_customers`, `spend`, `cac`, cumulative net revenue per customer by period |
| `mart_reconciliation` | day | source revenue vs mart revenue, order counts, delta % |

**Marts are fully rebuilt on every run.** At single-store scale (up to low millions of orders) a full rebuild takes minutes and is always correct when late refunds restate history. Only staging is incremental. Don't optimize further until a run exceeds 10 minutes.

---

## 6. Metric definitions

Every metric lives in `metrics.yml`. The Methodology page, the API's `/v1/metrics`, and the hover definitions on screen all read this one file.

| Metric | Definition |
|---|---|
| Cohort | Customers whose first qualifying order fell in the same month (or week), in the reporting timezone. |
| Customer retention, month N | Share of a cohort that placed at least one qualifying order in calendar month N after their first. Month 0 is 100% by construction and is shown as cohort size instead. |
| Revenue retention, month N | Cohort net revenue in month N ÷ cohort net revenue in month 0. Can exceed 100%. |
| Cumulative repeat, month N | Share of a cohort that had placed a second qualifying order by the end of month N. Never decreases, so it's the clearest curve to compare cohorts. |
| Time to second order | Days between first and second qualifying order, for customers who have one. Reported as median and 90th percentile. |
| Repeat within 90 days | Among customers whose first order is at least 90 days before the data cutoff, the share with a second qualifying order within 90 days. |
| Lapse threshold | 90th percentile of gaps between consecutive orders for customers with 2+ orders, clamped to 60–365 days. Admin can override. |
| Lapsed customer | Days since last qualifying order > lapse threshold. Lapse rate is the churn figure this product reports. |
| P(alive) | Probability the customer is still active, from the BG/NBD model. "Drifting" = P(alive) < 0.5 and not yet lapsed. |
| Historical LTV | Net revenue (after refunds) per customer. Reported at fixed ages (90, 180, 365 days after first order) so cohorts are comparable. |
| Predicted 12-month LTV | BG/NBD expected orders × Gamma-Gamma expected order value, as a p10–p90 range. Hidden when holdout error exceeds 30% (see §9.6). |
| RFM segment | Recency and Monetary scored 1–5 by quintile. Frequency uses fixed bands (1, 2, 3, 4–5, 6+) because most customers have exactly one order and quintiles collapse on ties. Named segments are regions of the R×F grid. |
| CAC | Channel spend in a month ÷ new customers from that channel that month. Shown only when spend data exists. |
| LTV:CAC | 365-day historical LTV ÷ CAC for cohorts old enough; otherwise predicted p50, labeled as predicted. |
| Payback month | First month in which cumulative net revenue per acquired customer × gross margin ≥ CAC. Gross margin is an admin setting, labeled as an assumption. |

Small cohorts: any rate with a denominator under 30 is shown with a Wilson 95% interval and muted text.

```yaml
# metrics.yml (excerpt)
- id: retention_rate
  label: Customer retention
  definition: Share of a cohort that bought again in a given month after their first order.
  formula: active_customers(cohort, N) / cohort_customers(cohort)
  model: mart_cohort_retention_monthly
  unit: percent
  caveats:
    - Month 0 is always 100% and is shown as cohort size instead.
    - Rates from fewer than 30 customers show an interval.
    - Recent cohorts have fewer observable months. Blank cells are not zero.

- id: lapse_rate
  label: Lapse rate
  definition: Share of customers whose last order is older than the store's lapse threshold.
  formula: count(is_lapsed) / count(customers)
  model: mart_customer_state
  unit: percent
  caveats:
    - The threshold comes from this store's own purchase gaps. See Settings for the current value.
```

---

## 7. Datasets

### 7.1 Primary demo: Online Retail II (UCI)

UK online retailer, Dec 2009 – Dec 2011, roughly a million line items, real repeat behaviour, so the heatmap and curves look like a working business.

Cleaning rules, implemented as a `datasets/online_retail_ii` ingest adapter (not ad-hoc notebook code):

- Drop rows without a Customer ID from customer metrics. Report the dropped share on the Data page, because it biases retention upward.
- Invoices starting with `C` are cancellations: map to refunds against the matching customer.
- Non-product stock codes (postage, manual adjustments, bank charges, marketplace fees) go to the excluded-lines seed.
- Reporting timezone `Europe/London`, currency GBP.
- Caveat stated in the demo: many customers are wholesalers, so repeat rates run higher than a typical D2C store.

### 7.2 Stress case: Olist (Kaggle)

Use `customer_unique_id`, never `customer_id` (which is per order). Roughly 3% of customers buy twice. This is useful: it proves the product still says something useful for a low-repeat business. The Summary page leads with time-to-second-order and first-product findings when the heatmap is mostly pale.

### 7.3 Test data: synthetic generator

A small generator with known parameters (cohort sizes, per-period repeat probabilities, refund rate, guest-checkout share, orders on month boundaries). Tests assert the marts reproduce the known answers within tolerance. This is the only way to test cohort logic against ground truth.

### 7.4 Real client data

| Platform | Approach | Gotchas |
|---|---|---|
| Shopify | GraphQL Admin API. Bulk operation (JSONL) for the historical backfill, paginated `updated_at` queries for daily increments with a 3-day overlap to catch late refunds. | Without the `read_all_orders` scope, only the last 60 days of orders are visible. Customer PII fields fall under Shopify's protected customer data rules. Sort both out before the engagement starts. |
| WooCommerce | REST API v3, `modified_after` for increments, `per_page=100` | Self-hosted stores vary in plugin-modified order statuses; map them in the qualifying-status setting. |
| Anything else | CSV export mapped onto the raw schema | Ask for order-level rows with customer email, timestamp with timezone, status, totals, refunds. |

Because the staging layer isolates each source, switching sources rewrites only `stg_*`.

---

## 8. Design system

### 8.1 Direction

Retention analysis is borrowed from actuarial life tables: rows of people who started together, counted as time passes. The product should feel like a precise, calm instrument, closer to a well-set statistical report than a marketing dashboard.

**The one bold thing is language.** Filters read as a sentence. The top of every page states what the numbers mean in a sentence. Every metric name is a link to its definition. Everything else is quiet: no decoration, no KPI card row, no gradients, no entrance animations.

**One consistent device: the highlighter.** Whatever the user has selected (a cohort row, a curve, the filter clause being edited) gets the same yellow highlighter mark, on every screen. Selection never uses any other colour.

### 8.2 Colour

| Token | Hex | Use |
|---|---|---|
| `ink` | `#18222D` | Primary text, axes, the selected curve |
| `graphite` | `#5A6672` | Secondary text, unselected labels |
| `rule` | `#D6DBDF` | Dividers, table rules, unselected curves |
| `ground` | `#EEF1F3` | App background |
| `sheet` | `#FFFFFF` | Data surfaces |
| `highlighter` | `#F4D35E` | Selection only. Never text, never data encoding. |
| `signal` | `#B3261E` | Errors and flagged anomalies only. Never data encoding. |

Retention ramp, single hue, light to dark, for the heatmap and RFM grid:

`#F1F5FA` `#D6E3F0` `#B0C8E1` `#82A7CC` `#5584B3` `#2F6296` `#17406E`

Rules:

- Data is encoded with **one sequential hue**. No green/amber/red: it fails colour-blind users and turns a measurement into a judgement the merchant didn't ask for.
- Cell text flips from `ink` to white at ramp step 5 and above. Check contrast for every step in a unit test.
- Comparison curves differ by **dash pattern** (solid, dashed, dotted), not colour. Maximum three pinned comparisons.

### 8.3 Typography

| Role | Family | Settings |
|---|---|---|
| Interface, numbers, tables | Public Sans | 400 / 500 / 600, `font-variant-numeric: tabular-nums` everywhere numbers appear |
| Findings, page titles, filter sentence | Source Serif 4 | 400 / 600, optical sizing on |

Scale (px): 12, 14, 16, 20, 26, 34. App body text is 14 for density; the Methodology page uses 16 with a 70-character measure.

Banned: all-caps labels, monospace for data, coloured or italic single words inside headings, labels stacked above every block.

### 8.4 Shape, space, depth

- Sheets: 6 px radius. Controls: 4 px. Filter clauses are underlined text, not pills.
- Hierarchy inside a sheet comes from type and 1 px rules, never nested cards.
- No shadows on sheets. Separation is `sheet` on `ground` with a 24 px gap. Popovers and menus get the only shadow: `0 8px 24px rgb(24 34 45 / 0.12)` plus a 1 px `rule` border.
- 4 px spacing base. Max content width 1440 px. Everything left-aligned; numbers right-aligned in tables.

### 8.5 Data visualisation rules

**Cohort table (heatmap)**

- Rendered as `<table>`: one row per cohort (oldest at top), one column per month since first order.
- First data column is cohort size with a thin inline bar, not "100%". The colour scale starts at month 1, so the darkest colour isn't wasted on a constant.
- Unobservable cells are empty `ground`, which forms a clean staircase at the lower right. Observed zeros show "0%" on the lightest ramp step.
- Rates from fewer than 30 customers use `graphite` text at reduced opacity; the tooltip gives the interval.
- Hover or focus on a cell: "318 of 1,204 customers bought again in month 3 (26.4%, 24.0–28.9%)."
- Arrow keys move between cells; Enter selects the cohort row (highlighter) and focuses its curve below.
- Measure toggle: customers / revenue / cumulative repeat.

**Curves**

- All cohorts drawn 1 px in `rule`. The median of the last six cohorts drawn 2 px in `graphite`. The selected cohort drawn 2 px in `ink` with a highlighter halo.
- Four horizontal gridlines, no chart border, no legend box. Direct labels at line ends.

**Never:** pie, donut, gauge, 3D, gradient fill, animated number count-ups.

### 8.6 Motion

- Motion only answers an action. Popover open: 120 ms fade. Cohort selected: the curve focus changes over 120 ms.
- On filter change, the previous numbers stay visible at reduced opacity until the new ones arrive, then swap without animation. A 2 px progress line appears at the top of the affected sheet only if the wait exceeds 300 ms.
- Skeletons only on first load, as static blocks in the shape of the final layout. No shimmer.
- `prefers-reduced-motion: reduce` removes all transitions.

### 8.7 Copy

- Plain verbs, sentence case, active voice. "Export CSV" produces a toast that says "CSV exported".
- Name things by what the merchant understands: "bought again", "first order", "customers who stopped buying". The precise metric name sits one hover away.
- Every page carries a data stamp: "Data through 4 Oct 2026, refreshed today at 02:10."
- Empty states direct: "No customers match these filters. Remove the country filter to see 1,204 customers."
- Errors say what happened and what to do: "Couldn't load cohorts: the server didn't respond within 10 seconds. Retry." No apologies, no vague "Something went wrong".
- Stale data is never silent: "Last night's refresh failed. Showing data through 3 Oct. Details on the Data page."

### 8.8 Findings

Generated by deterministic templates in the API from mart numbers. No LLM. Every sentence links to the view that proves it.

A finding is shown only when it clears a bar: the difference is outside the 95% interval of the comparison baseline (median of the previous six cohorts), and both sides have at least 30 customers. Maximum three per page, ordered by size of effect.

Examples:

- "Customers acquired in August bought again less often than usual: 21% by month 2, against 27% for the previous six cohorts."
- "Half of returning customers place their second order within 34 days. After 90 days, fewer than 1 in 10 still do."
- "Customers whose first order was in Candles came back within 90 days at twice the store average (31% vs 15%, 412 customers)."

### 8.9 Screens

**Shell**

```
+-------------+------------------------------------------------------------------+
| Store name  |  Monthly cohorts acquired Jan 2025 to Sep 2026, from all         |
|             |  channels, in all countries, counting revenue net of refunds.    |
| Summary     |  (each underlined clause opens a popover; < 768px it collapses   |
| Cohorts     |   to "Filters (3)")                                              |
| Repeat      +------------------------------------------------------------------+
| Segments    |                                                                  |
| Channels    |                         page content                             |
| Customers   |                                                                  |
|             |                                                                  |
| Methodology |                                                                  |
| Data        |                                                                  |
|             |                                                                  |
| Data through|                                                                  |
| 4 Oct 2026  |                                                                  |
+-------------+------------------------------------------------------------------+
```

**Summary**

```
+------------------------------------------------------------------+
| Findings (serif, up to three sentences, each linked)             |
+------------------------------------------------------------------+
| Vitals             Sep 2026    Aug 2026    Change                |
| New customers       1,204       1,311      -8%                   |
| Repeat in 90 days     27%         29%      -2 pts                |
| Lapse rate            41%         40%      +1 pt                 |
| 365-day LTV         £84         £81       +4%                    |
+------------------------------------------------------------------+
| Cohort table: last 12 cohorts x 12 months                        |
+------------------------------------------------------------------+
```

**Cohorts** — full cohort table above, linked curves below. Granularity (month/week) and measure (customers/revenue/cumulative repeat) toggles sit in the sheet header.

**Repeat** — time-to-second-order histogram with median and p90 marked and labeled in a sentence; first-product table: product or category, first-time buyers, repeat within 90 days with interval, difference from store average. Sorted by effect size, minimum 30 buyers.

**Segments** — 5×5 Recency × Frequency grid, cell shade = average monetary value, cell text = customer count, segment regions outlined and named directly on the grid. Clicking a region opens its customer list.

**Channels** — table: channel, new customers, CAC, 365-day LTV, predicted 12-month LTV range, LTV:CAC, payback month. Attribution coverage shown above the table ("62% of new customers have a known channel"). Without spend data, CAC columns are absent and a single line explains how to add spend.

**Customers** — virtualised table with filters from the URL; row opens a side panel with the customer's order timeline (dots on a time axis), RFM scores, P(alive), predicted LTV range. Viewers see masked emails; admins see full.

**Methodology** — rendered from `metrics.yml`: each metric's definition, formula, model name and caveats, plus current settings (timezone, currency, qualifying statuses, lapse threshold, gross margin).

**Data** — last 30 runs with status and duration, freshness, dbt test results, reconciliation against source revenue, identity-merge rate, dropped-row counts, CLV holdout error.

### 8.10 Component inventory

`AppShell`, `NavRail`, `FilterSentence`, `Clause`, `Sheet`, `SheetHeader`, `Finding`, `VitalsTable`, `CohortTable`, `CurveChart`, `Histogram`, `RfmGrid`, `DataTable`, `CustomerPanel`, `Term` (dotted underline that opens the metric definition), `DataStamp`, `EmptyState`, `ErrorState`, `FirstLoad`.

Each data component ships four states (loading, empty, error, ready) designed once and reused. No page styles its own table, card or chart.

### 8.11 Tokens

```css
:root {
  --ink: #18222D;
  --graphite: #5A6672;
  --rule: #D6DBDF;
  --ground: #EEF1F3;
  --sheet: #FFFFFF;
  --highlighter: #F4D35E;
  --signal: #B3261E;

  --ramp-1: #F1F5FA; --ramp-2: #D6E3F0; --ramp-3: #B0C8E1; --ramp-4: #82A7CC;
  --ramp-5: #5584B3; --ramp-6: #2F6296; --ramp-7: #17406E;

  --font-ui: "Public Sans", system-ui, sans-serif;
  --font-text: "Source Serif 4", Georgia, serif;

  --radius-sheet: 6px;
  --radius-control: 4px;
  --shadow-pop: 0 8px 24px rgb(24 34 45 / 0.12);

  --dur-quick: 120ms;
  --ease: cubic-bezier(0.2, 0, 0, 1);
}

@media (prefers-reduced-motion: reduce) {
  :root { --dur-quick: 0ms; }
}
```

### 8.12 Review checklist (run before every screen merges)

- [ ] No row of identical KPI cards
- [ ] No colour encodes data except the single ramp
- [ ] Highlighter used for selection and nothing else
- [ ] Every number uses tabular figures and the shared formatter (`Intl.NumberFormat`, locale and currency from `/v1/meta`)
- [ ] Every metric name is a `Term`
- [ ] Loading, empty and error states present
- [ ] Keyboard path through every control; visible focus ring
- [ ] Axe passes; contrast checked on every ramp step
- [ ] Works at 375 px wide

---

## 9. Backend

### 9.1 API surface

All routes under `/v1`, JSON, typed by Pydantic, documented by OpenAPI.

| Method | Route | Purpose | Role |
|---|---|---|---|
| GET | `/meta` | Data version, data-through date, timezone, currency, allowed dimension values, date bounds | viewer |
| GET | `/summary` | Findings + vitals | viewer |
| GET | `/cohorts/retention` | Cohort table; `granularity`, `measure`, `from`, `to`, dims | viewer |
| GET | `/cohorts/curves` | Curve series + median baseline | viewer |
| GET | `/repeat/second-order` | Histogram bins, median, p90 | viewer |
| GET | `/repeat/first-product` | First product/category repeat table | viewer |
| GET | `/segments/rfm` | 5×5 grid + segment totals | viewer |
| GET | `/segments/{segment}/customers` | Cursor-paginated customer list | viewer |
| GET | `/customers/{customer_key}` | Customer detail and timeline | viewer (masked) / admin |
| GET | `/channels` | Channel performance | viewer |
| GET | `/metrics` | Rendered `metrics.yml` + current settings | viewer |
| GET | `/data-health` | Runs, tests, reconciliation | viewer |
| POST | `/pipeline/runs` | Enqueue a manual refresh → `202` + run id | admin |
| GET | `/pipeline/runs/{id}` | Run status | admin |
| POST | `/exports` | Enqueue PDF export, or stream CSV directly | viewer (CSV), admin (PDF) |
| GET | `/exports/{id}` | Status + short-lived download URL | owner |
| PUT | `/settings` | Timezone, currency, statuses, thresholds; triggers rebuild | admin |
| GET | `/healthz`, `/readyz` | Liveness; readiness checks DB and data version | none |

**Response envelope**

```json
{
  "data": {
    "periods": [0, 1, 2, 3],
    "cohorts": [
      {
        "cohort": "2026-03",
        "size": 1204,
        "active": [1204, 318, 251, 230],
        "rate": [1.0, 0.264, 0.208, 0.191],
        "low": [1.0, 0.240, 0.186, 0.170],
        "high": [1.0, 0.289, 0.232, 0.214]
      }
    ]
  },
  "meta": {
    "data_version": "2026-10-05T02:10:44Z/418",
    "data_through": "2026-10-04",
    "timezone": "Europe/London",
    "currency": "GBP",
    "filters": { "granularity": "month", "channel": ["all"] },
    "metrics": ["retention_rate"]
  }
}
```

Columnar arrays keep the full heatmap payload small. Arrays end where observability ends; the client never invents zeros.

**Errors** use RFC 9457 `application/problem+json` with a stable `type`, a human `detail` the UI can show verbatim, and the `request_id`.

**Validation.** Dimension values are validated against `/meta`'s allowed lists, dates are clamped to data bounds, unknown parameters are rejected. All SQL goes through SQLAlchemy Core with bound parameters. There is no string-built SQL anywhere in the API.

### 9.2 Speed

- **Data-version cache.** The API holds the current `data_version` in memory, updated by `LISTEN data_published` on a direct (non-pooled) connection, with a 30-second poll as fallback. Responses are cached in-process (LRU) keyed by `(data_version, route, normalized params)`. A publish changes the version, so invalidation is automatic.
- **ETags.** `ETag = hash(data_version, route, params)`. Repeat requests get `304`. `Cache-Control: private, max-age=60, stale-while-revalidate=600`.
- **Compression.** Brotli/gzip for responses over 1 KB.
- **Pooling.** asyncpg pool of 5–10 through the provider's pooled endpoint. `statement_timeout = 5s` on the API role.
- **Indexes.** Marts are small; composite indexes in §5.4 cover every filter path. `EXPLAIN` of each route's query is checked in once and reviewed when marts change.

### 9.3 Pipeline: idempotent, locked, publish-or-nothing

One job type, `refresh`, run by the worker:

1. Take `pg_advisory_lock('refresh')`. A second refresh request while one runs returns the existing run id.
2. **Ingest** each source from its stored cursor with a 3-day overlap. Upserts are idempotent (§5.1). Cursor advances only after the batch commits.
3. **Build** with `dbt build --target build` into `analytics_build` (custom `generate_schema_name` so dbt writes exactly there).
4. **Audit**, all must pass:
   - every dbt test, including custom ones: period-0 active equals cohort size; no rate above 1; no negative revenue in marts
   - reconciliation: mart net revenue vs raw net revenue for the last 90 days within 0.5%
   - row-count guard: no mart shrinks by more than 20% versus the published version without an admin override
5. **Publish** in one transaction:

   ```sql
   set local lock_timeout = '5s';
   alter schema analytics       rename to analytics_prev;
   alter schema analytics_build rename to analytics;
   drop schema analytics_prev cascade;
   insert into ops.data_versions (version, run_id, data_through, published_at)
   values ($1, $2, $3, now());
   notify data_published;
   ```

   On lock timeout, retry three times with backoff, then fail the run without touching `analytics`.
6. **Report**: write `ops.pipeline_runs` (status, durations per step, test results, reconciliation numbers) and post a one-line summary to the webhook. Failures alert immediately.

Scheduling: the worker enqueues one `refresh` per day at a configured local time. `ops.jobs` has a unique key on `(kind, scheduled_for)`, so restarts and double-schedules can't create duplicate runs.

The weekly `clv_fit` job reads the published marts, fits BG/NBD + Gamma-Gamma, writes `mart_customer_clv` through the same build-audit-publish path.

### 9.4 Jobs

`ops.jobs(id, kind, payload, status, scheduled_for, attempts, locked_at, error, created_by)`. Workers claim with `select … for update skip locked`. Retries with exponential backoff, max 3. Jobs older than 30 days are pruned. This covers refresh, CLV fit and PDF export without adding Redis.

### 9.5 Auth and security

- **Users**: invite-only allowlist in `ops.users` with role. First admin from `BOOTSTRAP_ADMIN_EMAIL`.
- **Web → API**: Next.js server mints a 5-minute JWT (`sub`, `role`, `exp`) signed with a key shared only with the API. The client gets it from a same-origin route and refreshes it before expiry. The API verifies every request and enforces roles itself.
- **Database roles**: `api_ro` (SELECT on `analytics`, limited `ops`), `pipeline_rw`, `migrator`. The API cannot write.
- **Config, not code**: OAuth redirect URLs, allowed CORS origins, API base URL all come from environment variables per environment. Nothing environment-specific is hardcoded.
- **Secrets**: never committed; gitleaks in pre-commit and CI; rotation steps in the runbook. Platform tokens (Shopify, Woo) stored as env vars on the worker only.
- **PII**: email → HMAC in staging; raw emails stay in `raw` only, which `api_ro` cannot read except via an admin-only masked view.
- **Audit log**: settings changes, manual refreshes, exports, user changes.
- Dependabot on both ecosystems; rate limiting on auth routes and export creation.

### 9.6 CLV model governance

- Calibrate on data up to `cutoff − 180 days`, predict the next 180 days, compare with actual per cohort.
- Report MAPE of cohort-level predicted vs actual revenue on the Data page.
- If MAPE > 30%, the predicted-LTV column is hidden with a line explaining why. Showing a bad prediction is worse than showing none.
- `model_version` is stored with every prediction.

### 9.7 Exports

- **CSV**: streamed straight from the API (`StreamingResponse`) for any table view, honoring current filters. Masked for viewers.
- **PDF**: `POST /exports` enqueues a job. The worker opens `/print/<view>?<filters>` in headless Chromium with a one-time token, waits for a `data-ready` attribute, prints A4/Letter with print CSS, uploads to object storage, and returns a signed URL valid for 24 hours. The print route reuses the same components; there is no second template.

### 9.8 Observability

- JSON logs with `request_id`, `user_id`, `data_version`, route, duration.
- Sentry in all three services, with releases tied to git SHAs.
- Uptime check on `/readyz` every minute.
- The Data page is the client-facing view of all of this.

---

## 10. Frontend architecture

- **Routes**: `(app)` for the product, `(print)` for PDF rendering, `(auth)` for sign-in.
- **First paint**: Server Components fetch through the generated client with the server-side token, then hand data to TanStack Query via `HydrationBoundary`. No loading flash on navigation to a page whose data is already cached.
- **Interactions**: TanStack Query with `placeholderData: keepPreviousData`; `staleTime` aligned with the API's `max-age`; query keys include `data_version` from `/meta` so a new publish refetches everything once.
- **State**: nuqs holds every filter in the URL with typed parsers generated from the OpenAPI schema. No filter state anywhere else.
- **Errors**: one error boundary per sheet; a failed chart never blanks the page.
- **Formatting**: one `format.ts` (numbers, percentages with points vs percent change, currency, dates in the reporting timezone).
- **Performance**: fonts self-hosted via `next/font` with `display: swap`; visx imported per-module; customer tables virtualised.

---

## 11. Testing and CI gates

| Layer | What | Tool |
|---|---|---|
| dbt unit | Cohort assignment for: refund-only first order, guest merged by email, order at 00:30 local on the 1st, current-month cohort excluded, customer skipping months | dbt unit tests with fixtures |
| dbt data | unique / not null / relationships; custom invariants (§9.3) | dbt tests |
| Ground truth | Synthetic generator → marts reproduce known rates within tolerance | pytest |
| Independent check | Online Retail II heatmap matches a separate pandas computation within 0.1 pt | pytest |
| API | Route behaviour against a real Postgres; property-based fuzzing from the OpenAPI schema | pytest + testcontainers, Schemathesis |
| Math | Wilson intervals, rate aggregation, finding thresholds | pytest |
| Frontend unit | Formatters, scales, contrast of every ramp step | Vitest |
| End-to-end | Sign in, change filters, select cohort, open definition, export CSV, viewer cannot trigger refresh | Playwright |
| Accessibility | Every page | axe via Playwright |

CI fails on: ruff, pyright, sqlfluff, dbt build + tests on fixtures, pytest, TypeScript, lint, generated-client drift, Playwright smoke, axe, gitleaks.

---

## 12. Performance budgets

| Measure | Budget |
|---|---|
| API p95, cache hit | < 50 ms |
| API p95, cache miss | < 300 ms |
| Cohort table payload (36 × 36, gzip) | < 30 KB |
| Largest Contentful Paint, desktop broadband | < 1.5 s |
| Interaction to Next Paint | < 200 ms |
| JS per route (gzip) | < 180 KB |
| Full refresh, Online Retail II | < 3 min |
| Daily incremental refresh | < 1 min |

Measured in CI where possible (Lighthouse CI on preview deploys, k6 smoke against staging) and on the Data page in production.

---

## 13. Repository and workflow

```
retention/
  apps/
    web/                Next.js app
    api/                FastAPI service
  pipeline/
    ingest/             adapters: shopify, woocommerce, csv, datasets/online_retail_ii, datasets/olist
    dbt/                staging, intermediate, marts, macros, seeds, unit tests
    clv/                PyMC-Marketing fit + holdout
    worker/             job runner, scheduler, PDF export
    synth/              synthetic data generator
  metrics/metrics.yml   single source of metric definitions
  infra/
    docker-compose.yml  postgres, api, worker, web for local dev
    migrations/         Alembic, ops schema only
    render.yaml         (or equivalent) service definitions
  docs/
    erd.md
    adr/                one file per architectural decision
    runbook.md
  justfile
```

Python via a uv workspace (api, pipeline share a small `core` package for settings and DB roles). Node via pnpm.

```
just up            # compose up: postgres, api, worker, web
just seed retail   # load Online Retail II and run a full refresh
just test          # everything CI runs
just gen           # regenerate TS client from OpenAPI
```

---

## 14. Environments and deployment

| Environment | Web | API + worker | Database |
|---|---|---|---|
| Local | `next dev` | compose | compose Postgres |
| Preview | Vercel preview per PR | shared staging services | staging database (or a provider branch per PR) |
| Production | Vercel | two always-on small instances | managed Postgres with point-in-time restore |

- No free tiers that sleep or wipe disk in production.
- Before the client-data swap, branch or snapshot the production database.
- Hosting cost for one client is in the low tens of USD a month; confirm current pricing when quoting.

---

## 15. Build plan

| # | Phase | Days | Exit criteria |
|---|---|---|---|
| 1 | Foundations | 3 | `just up && just seed retail` produces raw tables; CI runs; ops schema migrated |
| 2 | Data layer | 6 | All marts built; unit tests and invariants pass; synthetic ground-truth and pandas cross-check pass; build-audit-publish works and survives a deliberately failing test |
| 3 | API | 4 | All routes live; OpenAPI published; TS client generated; cache + ETag verified; p95 within budget on seed data |
| 4 | Design system | 4 | Tokens, fonts, `FilterSentence`, `CohortTable`, `CurveChart`, `DataTable`, `Term`, all four states for each; review checklist passes on a components page |
| 5 | Screens | 8 | All eight screens on live data; findings engine with thresholds |
| 6 | Auth, roles, exports, Data page | 4 | Invite flow; role enforcement tested at the API; CSV and PDF exports; Data page complete |
| 7 | Hardening | 3 | Playwright + axe green; performance budgets met; Sentry and uptime live; runbook written |
| 8 | Deploy and handoff | 2 | Production deploy; walkthrough video; handoff package delivered |
| | **Total** | **34** | Roughly 7–9 weeks at part-time pace |
| 9 | Client data swap | 3–5 | Scoped separately once the export or API access is in hand; numbers reconcile with the client's own reports |

---

## 16. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Client data has no acquisition channel | "unattributed" dominates the Channels page | Derive from first-order UTM, referrer, discount code; show coverage % above the table |
| Guest checkouts and multiple emails | Retention under-counted | HMAC email merge; merge rate on the Data page |
| Low-repeat business | Heatmap mostly pale | Summary leads with second-order timing and first-product findings |
| Mixed currencies | Revenue metrics wrong | FX conversion at order date in staging; reporting currency is a setting |
| No spend data | CAC and LTV:CAC meaningless | Hide those columns and explain how to add spend; never show zero CAC |
| Shopify 60-day order limit | Cohorts start two months ago | Request `read_all_orders` before kickoff |
| Schema swap blocked by long queries | Publish delayed | `lock_timeout`, retry, API `statement_timeout` of 5 s |
| Late refunds restate history | Yesterday's numbers change | Full mart rebuild + 3-day ingest overlap; data version changes visibly |
| Scope creep into ML churn | Timeline slips | Out of scope in writing; BG/NBD covers "who's drifting" |

---

## 17. Handoff package

- Repository with the layout in §13 and a README that gets a new developer to a seeded local dashboard in under 15 minutes
- `metrics.yml` and the in-app Methodology page
- ERD of `raw`, `analytics`, `ops`
- OpenAPI docs (Swagger UI) and the generated TypeScript client
- ADRs for every decision in §0
- Runbook: environment variables, accounts, manual refresh, reading the Data page, rotating secrets, restoring the database, swapping a data source
- A short video walkthrough for non-technical users

---

## 18. References

- Next.js: https://nextjs.org/docs
- Tailwind CSS: https://tailwindcss.com/docs
- Radix Primitives: https://www.radix-ui.com/primitives
- visx: https://airbnb.io/visx
- TanStack Query: https://tanstack.com/query/latest
- openapi-typescript: https://openapi-ts.dev
- FastAPI: https://fastapi.tiangolo.com
- dbt: https://docs.getdbt.com
- PyMC-Marketing (CLV): https://www.pymc-marketing.io
- Online Retail II (UCI): https://archive.ics.uci.edu/dataset/502/online+retail+ii
- Olist Brazilian E-Commerce (Kaggle): https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- Shopify bulk operations: https://shopify.dev/docs/api/usage/bulk-operations/queries
- WooCommerce REST API: https://woocommerce.github.io/woocommerce-rest-api-docs/
- RFC 9457, Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- CVE-2025-29927, Next.js middleware authorization bypass: https://nvd.nist.gov/vuln/detail/CVE-2025-29927
