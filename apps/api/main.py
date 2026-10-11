"""FastAPI app: read-only API over the published marts."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import errors
from apps.api.db import db
from apps.api.routes import (
    channels,
    cohorts,
    data_health,
    exports,
    health,
    meta,
    pipeline,
    repeat,
    segments,
    summary,
    users,
)
from core.config import get_env
from core.logging import init_sentry, setup_logging

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    env = get_env()
    setup_logging()
    init_sentry(env.sentry_dsn, env.git_sha, env.app_env)
    if not env.api_jwt_secret:
        raise RuntimeError("API_JWT_SECRET is not set")
    await db.start()
    yield
    await db.stop()


app = FastAPI(
    title="Retention API",
    version="1.0.0",
    description="Cohort and retention metrics over published marts. Every number links to a definition in /v1/metrics.",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_exception_handler(errors.Problem, errors.problem_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, errors.validation_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, errors.http_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, errors.unhandled_handler)

app.add_middleware(BrotliMiddleware, minimum_size=1024, gzip_fallback=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_env().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "If-None-Match", "X-Request-ID"],
    expose_headers=["ETag", "X-Data-Version", "X-Request-ID", "Content-Disposition"],
    max_age=600,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = rid
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    response.headers["X-Request-ID"] = rid
    response.headers["Server-Timing"] = f"app;dur={ms}"
    if request.url.path not in ("/healthz", "/readyz"):
        log.info(
            "request",
            extra={
                "request_id": rid,
                "route": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": ms,
                "user_id": getattr(request.state, "user_id", None),
                "data_version": getattr(request.state, "data_version", None)
                or (db.current.version if db.current else None),
            },
        )
    return response


for module in (
    health,
    meta,
    summary,
    cohorts,
    repeat,
    segments,
    channels,
    data_health,
    pipeline,
    exports,
    users,
):
    app.include_router(module.router)
