# One file drives everything.  `just` lists the recipes.
set dotenv-load := true
set positional-arguments := true

compose := "docker compose -f infra/docker-compose.yml"
test_admin := "postgresql://postgres:" + env_var_or_default("POSTGRES_PASSWORD", "postgres") + "@localhost:5433/postgres"

default:
    @just --list

# Copy .env.example to .env with fresh random secrets (first run only).
init:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f .env ]; then echo ".env already exists"; exit 0; fi
    cp .env.example .env
    for key in POSTGRES_PASSWORD MIGRATOR_PASSWORD PIPELINE_PASSWORD API_RO_PASSWORD API_OPS_PASSWORD WEB_AUTH_PASSWORD PII_KEY API_JWT_SECRET EXPORT_SIGNING_KEY AUTH_SECRET; do
      old=$(grep "^${key}=" .env | cut -d= -f2-)
      new=$(openssl rand -hex 24)
      sed -i.bak "s|${old}|${new}|g" .env
    done
    rm -f .env.bak
    echo "wrote .env"

# Start postgres, api, worker and web (http://localhost:3000).
up:
    {{compose}} up -d --build

down:
    {{compose}} down

logs service="":
    {{compose}} logs -f {{service}}

# Load a public dataset and run a full refresh: retail (default) or olist.
seed dataset="retail" *flags="":
    {{compose}} run --rm worker python -m pipeline.ingest seed {{dataset}} {{flags}}

# Build, audit and publish now.
refresh:
    {{compose}} run --rm worker python -m pipeline.worker refresh

# Fit the CLV model now (normally weekly).
clv:
    {{compose}} run --rm worker python -m pipeline.worker clv

# Load marketing spend from a CSV (date, channel, spend_amount, currency), then refresh.
spend file:
    {{compose}} run --rm -v "$(pwd)/{{file}}:/tmp/spend.csv:ro" worker python -m pipeline.ingest spend /tmp/spend.csv
    just refresh

migrate:
    {{compose}} run --rm migrate

# Everything CI runs, against the local compose Postgres.
test: lint test-py test-web

test-py *args="":
    TEST_ADMIN_DATABASE_URL="{{test_admin}}" uv run pytest {{args}}

test-web:
    cd apps/web && pnpm test

# End-to-end and accessibility against the running stack (just up && just seed retail first).
e2e:
    cd apps/web && pnpm exec playwright test

lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run sqlfluff lint pipeline/dbt/models pipeline/dbt/tests
    cd apps/web && pnpm lint && pnpm typecheck

# Regenerate the TypeScript client from the API's OpenAPI schema.
gen:
    uv run python scripts/export_openapi.py
    cd apps/web && pnpm gen

# Web app with hot reload against the compose API (run `just up` first).
web-dev:
    cd apps/web && pnpm dev

# dbt directly against the build schema, e.g. `just dbt build --select stg_orders+`.
dbt *args:
    {{compose}} run --rm worker python -m pipeline.worker dbt {{args}}
