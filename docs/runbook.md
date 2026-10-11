# Runbook

For whoever operates the platform after handoff. Commands assume the repository root and
[`just`](https://github.com/casey/just); production equivalents are noted.

## Services and accounts

| Piece | Where | Notes |
|---|---|---|
| Web (Next.js) | Vercel | Env vars below; `PUBLIC_API_URL` is the API's public URL |
| API (FastAPI) | always-on instance (`infra/render.yaml`) | `/readyz` is the uptime check |
| Worker | always-on background instance | runs the daily refresh, weekly CLV fit, PDF exports |
| Postgres 16 | managed (Neon or equivalent), PITR on | roles from `infra/db/roles.sql` |
| Object storage (optional) | any S3-compatible | PDF exports; without it, files live in `ops.export_files` |
| Sentry | three projects or one with environments | set `SENTRY_DSN` (api, worker, web server) and `NEXT_PUBLIC_SENTRY_DSN` (browser, build time) |
| Webhook | Slack-compatible incoming webhook | `PIPELINE_WEBHOOK_URL`; one line per run, failures immediately |

## Environment variables

`.env.example` lists every variable with a comment. By service:

- **All**: `APP_ENV`, `GIT_SHA`, `SENTRY_DSN`.
- **API**: `API_DATABASE_URL` (api_ro), `API_OPS_DATABASE_URL` (api_ops), `API_JWT_SECRET`,
  `EXPORT_SIGNING_KEY`, `CORS_ALLOWED_ORIGINS`, `S3_*` (optional).
- **Worker**: `PIPELINE_DATABASE_URL` (pipeline_rw), `MIGRATOR_DATABASE_URL` (migrations only),
  `PII_KEY`, `API_JWT_SECRET` (mints print tokens), `WEB_BASE_URL`, `PIPELINE_WEBHOOK_URL`,
  `BOOTSTRAP_ADMIN_EMAIL`, `SHOPIFY_*` / `WOO_*`, `S3_*`.
- **Web**: `WEB_DATABASE_URL` (web_auth), `API_BASE_URL` (server to API), `PUBLIC_API_URL`
  (browser to API), `API_JWT_SECRET`, `AUTH_SECRET`, `AUTH_GOOGLE_ID/SECRET`, `EMAIL_SERVER`,
  `EMAIL_FROM`, `AUTH_TRUST_HOST`. Never set `AUTH_DEV_LOGIN` in production (it is also refused
  when `APP_ENV=production`).

## First deployment

1. Create the database, then run the roles script as the owner:
   `psql "$ADMIN_URL" -v dbname=retention -v migrator_password=… -v pipeline_password=… -v api_ro_password=… -v api_ops_password=… -v web_auth_password=… -f infra/db/roles.sql`
2. Migrate: `alembic -c infra/migrations/alembic.ini upgrade head` with `MIGRATOR_DATABASE_URL`
   (the worker image contains Alembic; on Render this is the worker's pre-deploy command).
3. Deploy API and worker, then the web app. Set `BOOTSTRAP_ADMIN_EMAIL`: the worker invites that
   address as the first admin when `ops.users` is empty.
4. Load data: platform credentials in the worker env and `python -m pipeline.ingest live`, or a
   CSV folder with `python -m pipeline.ingest csv <folder>`, then trigger a refresh (Data page →
   Refresh now, or `python -m pipeline.worker refresh`).

## Daily operation

- The worker enqueues one refresh per day at `refresh_time_local` (Settings) and one CLV fit per
  week. A webhook line reports each outcome.
- **Manual refresh**: Data page → Refresh now (admins), `POST /v1/pipeline/runs`, or `just refresh`.
  A second request while one is queued or running returns the same job.
- **Marketing spend**: `just spend path/to/spend.csv` (columns: date, channel, spend_amount,
  currency). Channel names must match the acquisition channels shown on the Channels page.

## Reading the Data page

| Panel | Healthy | If not |
|---|---|---|
| Freshness | "Up to date", data through yesterday | "Last night's refresh failed": the dashboard still shows the previous data. Open the latest run below. |
| Tests | failures 0 | The run lists failing tests. Fix the data or the definition and refresh. |
| Reconciliation | difference under 0.5% | A larger gap blocks publishing. Usually missing FX rates or a source change. |
| Customers and identity | guest merge rate stable; "missing exchange rate" 0 | Missing FX means the reference-rate feed was unreachable; the next refresh retries. |
| Dropped rows | shares stable between runs | A jump means the source export changed shape. |
| Prediction check | MAPE under 30% | Above 30% predicted LTV is hidden automatically. |
| Last 30 runs | "Published" with steps in seconds | A failed step shows its error; the build schema is kept for inspection until the next run. |

A run failing with "marts shrank by more than 20%" is the row-count guard. If the shrink is
expected (a data source was replaced), run `python -m pipeline.worker refresh --allow-shrink`.

## Rotating secrets

| Secret | How | Effect |
|---|---|---|
| Role passwords | re-run `roles.sql` with new values, update the URLs, restart | none |
| `API_JWT_SECRET` | update web, API and worker together, restart | open sessions fetch a new API token on their next request |
| `AUTH_SECRET` | update web, restart | everyone signs in again |
| `EXPORT_SIGNING_KEY` | update API, restart | existing download links stop working |
| `PII_KEY` | update worker, then refresh | guest-only customers (keys starting `e:`) get new keys; registered customers (`c:`) are unchanged. CLV predictions for `e:` customers return after the next weekly fit. |
| Platform tokens | update worker env, restart | none |

gitleaks runs in pre-commit and CI. If a secret is ever committed, rotate it first, then rewrite
history.

## Restoring the database

1. In the provider console, restore to a point in time before the incident into a new branch or
   instance.
2. Point `PIPELINE_DATABASE_URL`, `API_DATABASE_URL`, `API_OPS_DATABASE_URL`, `WEB_DATABASE_URL`
   and `MIGRATOR_DATABASE_URL` at it and restart the services.
3. Run a refresh to rebuild the marts from `raw` (`raw` is the system of record; marts are
   always derivable).

Before swapping in a client's real data, branch or snapshot production first.

## Swapping a data source

Only the adapter and `pipeline/dbt/macros/normalize_sources.sql` know a source's shape.

1. Shopify: set `SHOPIFY_SHOP` and `SHOPIFY_ACCESS_TOKEN` (scopes `read_orders`,
   `read_all_orders`, `read_customers`; without `read_all_orders` only 60 days are visible).
   The first run backfills with a bulk operation; later runs read `updated_at` with a 3-day overlap.
2. WooCommerce: set `WOO_BASE_URL`, `WOO_CONSUMER_KEY`, `WOO_CONSUMER_SECRET`. Map plugin-specific
   statuses in Settings → qualifying statuses.
3. Anything else: export the CSVs described in `pipeline/ingest/adapters/csv_drop.py`.
4. Set the reporting timezone and currency in Settings, then refresh with `--allow-shrink` (the
   marts are replaced), and check the Reconciliation panel against the platform's own revenue report.

## Useful queries

```sql
-- latest runs
select id, kind, status, trigger, started_at, finished_at, error from ops.pipeline_runs order by id desc limit 10;
-- what is live
select * from ops.data_versions order by published_at desc limit 1;
-- queue
select id, kind, status, attempts, run_after, error from ops.jobs where status in ('queued', 'running');
```
