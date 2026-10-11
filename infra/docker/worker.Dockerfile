# Worker: ingest, dbt build/audit/publish, CLV fit, PDF export. Build context: repo root.
FROM python:3.12-slim-bookworm AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /uvx /bin/
# g++ lets PyTensor compile its C backend; without it CLV fits are an order of magnitude slower.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group pipeline
# Chromium for PDF exports.
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*

FROM base AS runtime
COPY core core
COPY pipeline pipeline
COPY metrics metrics
COPY infra/migrations infra/migrations
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/data /home/app/.cache \
 && cp -r /root/.cache/ms-playwright /home/app/.cache/ \
 && chown -R app /app/data /home/app/.cache
USER app
ENV PYTENSOR_FLAGS=base_compiledir=/tmp/pytensor
CMD ["python", "-m", "pipeline.worker"]

# Test image: same runtime plus dev tools (pytest, sqlfluff, ...).
FROM base AS dev
RUN uv sync --frozen --no-default-groups --group pipeline --group api --group dev
COPY . .
ENV PYTENSOR_FLAGS=base_compiledir=/tmp/pytensor
CMD ["pytest", "-q"]
