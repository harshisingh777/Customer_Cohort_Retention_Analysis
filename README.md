# Retention

Cohort and retention analytics for a single e-commerce store. It answers "are the customers we pay
to acquire coming back, and which ones?" for a founder or marketing lead, in under a minute,
with every number linked to its definition and reconciled with the source.

- **Summary**: findings in plain language, vitals against the previous period, the last 12 cohorts.
- **Cohorts**: the cohort table (customers, revenue or cumulative repeat; monthly or weekly) and
  linked curves against the median of the last six cohorts.
- **Repeat**: time to second order; which first purchase brings customers back.
- **Segments**: recency × frequency grid with named segments.
- **Channels**: CAC, 365-day LTV, predicted 12-month LTV range, LTV:CAC, payback month.
- **Customers**: everyone, with status (still buying, drifting, stopped) and an order timeline.
- **Methodology**: every definition, rendered from `metrics/metrics.yml`.
- **Data**: freshness, test results, reconciliation, identity merge rate, dropped rows, model check.

## Quick start (about 10 minutes)

Needs Docker, [`just`](https://github.com/casey/just) and `openssl`.

```bash
just init            # .env from .env.example with random secrets
just up              # postgres, api, worker, web
just seed retail     # downloads Online Retail II (45 MB), loads, builds, publishes, fits the CLV model
```

Open http://localhost:3000 and use **Development sign-in** with `admin@example.com` (the
bootstrap admin). Other data: `just seed olist` (put the Kaggle CSVs in `data/olist/` first), or your
own store via `python -m pipeline.ingest csv <folder>` (see "Using your own data" below).

Without `just`: `cp .env.example .env` (replace every `change-me` value), then
`docker compose -f infra/docker-compose.yml up -d --build` and
`docker compose -f infra/docker-compose.yml run --rm worker python -m pipeline.ingest seed retail`.

## How it works

```
platform / CSV / dataset ─▶ [worker] ingest ─▶ raw.*  (idempotent upserts, full payloads)
                                        │
                                        ▼
                  [worker] dbt build ─▶ analytics_build.*  (staging → intermediate → marts)
                                        │
                  audit: dbt tests + invariants, reconciliation ≤ 0.5%, row-count guard
                        pass │                              │ fail
                             ▼                              ▼
     atomic swap analytics_build → analytics      keep yesterday's data, alert,
     ops.data_versions, NOTIFY data_published     Data page shows "stale since"
                             │
                             ▼
     [api] FastAPI, read-only role, cache keyed by data version, ETag/304
                             │
                             ▼
     [web] Next.js: server-rendered first paint, TanStack Query after, URL holds all state
```

| Part | Path | Stack |
|---|---|---|
| Web | `apps/web` | Next.js 16 (App Router), React 19, TypeScript strict, Tailwind 4 with CSS tokens, Radix, visx + d3-scale, TanStack Query/Table/Virtual, nuqs, Auth.js v5 |
| API | `apps/api` | FastAPI, Pydantic v2, SQLAlchemy 2 Core + asyncpg; all arithmetic in `metrics_math.py` |
| Pipeline | `pipeline/` | ingest adapters, dbt-core + dbt-postgres, PyMC-Marketing CLV, job worker, PDF export (Playwright) |
| Definitions | `metrics/metrics.yml` | the only place a metric is defined; read by the API, the Methodology page and every on-screen definition |
| Infra | `infra/` | compose for local dev, Alembic migrations (ops/auth only), roles SQL, Dockerfiles, `render.yaml` |
| Docs | `docs/` | ERD, runbook, ADRs, walkthrough script |

Ownership: ingest writes `raw`, dbt writes `analytics` and `pii`, Alembic owns `ops` and `auth`.
The API reads marts with a read-only role, and the web app never touches data directly.

## Using your own data

Export your store's orders as CSV files into one folder (columns are listed in
`pipeline/ingest/adapters/csv_drop.py`: at least `orders.csv`, ideally also `order_items.csv`,
`refunds.csv`, `customers.csv`), then:

```bash
docker compose -f infra/docker-compose.yml run --rm -v "/path/to/folder:/import:ro" worker python -m pipeline.ingest csv /import
just refresh
```

Set your timezone, currency and qualifying order statuses in Settings first. For Shopify or
WooCommerce, put the API credentials in `.env` and the daily refresh pulls them; see `docs/runbook.md`.

## Commands

| | |
|---|---|
| `just up` / `just down` / `just logs api` | stack |
| `just seed retail\|olist` | load a dataset and publish |
| `just refresh` | build, audit and publish now |
| `just clv` | refit the CLV model now (normally weekly) |
| `just spend file.csv` | load marketing spend, then refresh |
| `just test` | lint + Python tests + web unit tests |
| `just e2e` | Playwright smoke, axe and 375 px checks against the running stack |
| `just gen` | regenerate `openapi.json` and the TypeScript types |
| `just dbt build --select stg_orders+` | dbt with the worker's connection and current settings |
| `just web-dev` | Next.js dev server (copy the web variables from `.env` into `apps/web/.env.local`, with `localhost:5433` for the database and `localhost:8000` for the API) |

API docs (Swagger UI): http://localhost:8000/docs. Every route needs a bearer token from the web
app's `/api/token`.

## Testing

| Layer | What | Where |
|---|---|---|
| dbt unit | refund-only first order, guest merged by email, 00:30 local on the 1st, current-month cohort excluded, customer skipping months | `pipeline/dbt/models/_unit_tests.yml` |
| dbt data | unique/not-null/accepted values; invariants: period-0 active = cohort size, no rate above 1, no negative revenue, marts reconcile to orders | `pipeline/dbt/tests/` |
| Independent check | Online Retail II heatmap = separate pandas computation (300 cells, 0.0 pt difference) | `tests/pipeline/test_retail_crosscheck.py` |
| Publish safety | a deliberately failing test, a shrink and a reconciliation miss each leave the published data untouched | `tests/pipeline/test_publish.py` |
| API | auth, roles from the allowlist, validation, additivity, ETags, masking, pagination, exports | `tests/api/` |
| Math | Wilson intervals (property-based), percentiles, thresholds, payback | `tests/math/` |
| Web unit | formatters, query building, contrast of every ramp step | `apps/web/tests/unit/` |
| End to end | sign in, filters in the URL, keyboard cohort selection, definitions, CSV export, viewer can't refresh, axe on every page, 375 px | `apps/web/tests/e2e/` |
| Fuzzing | Schemathesis over every GET route (CI) | `.github/workflows/ci.yml` |

Python tests need a Postgres superuser URL: `just test-py` uses the compose database and creates
a throwaway `retention_test` database. Tests load Online Retail II (downloaded to `data/` on first use).

## Measured on the demo data

| Budget | Target | Measured |
|---|---|---|
| API p95, cache hit | < 50 ms | 3 ms |
| API p95, cache miss | < 300 ms | 25 ms |
| Cohort table payload (gzip) | < 30 KB | 3.4 KB monthly; weekly under 30 KB (tested) |
| Largest Contentful Paint | < 1.5 s | 0.14–0.52 s (local) |
| JS per route (gzip) | < 180 KB | 12–26 KB per route after the first; 200 KB on a cold first load, of which 111 KB is the shared React and Next.js runtime |
| Full refresh, Online Retail II | < 3 min | about 30 s (dbt build); seed with CLV fit about 4 min |

## Security

Invite-only sign-in; the API verifies a 5-minute JWT on every request and takes roles from its
own allowlist. Database roles separate reading, admin writes, the pipeline and migrations. Emails
become HMAC-SHA256 hashes in staging; viewers see masked emails. Secrets come from the
environment only; gitleaks runs in pre-commit and CI. See `docs/adr/0011-auth-and-roles.md` and
`docs/adr/0013-pii-hmac.md`.

## More

- `docs/runbook.md`: environment variables, deployment, manual refresh, reading the Data page,
  rotating secrets, restoring the database, swapping a data source.
- `docs/erd.md`: the `raw`, `analytics` and `ops` schemas.
- `docs/adr/`: one record per design decision, including deviations from the build spec
  (`0018-implementation-notes.md`).
