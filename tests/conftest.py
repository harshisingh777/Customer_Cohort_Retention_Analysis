"""Shared fixtures.

Database tests run against a throwaway database `retention_test` on a real Postgres:
- TEST_ADMIN_DATABASE_URL (a superuser URL; CI and local compose), or
- a testcontainers Postgres when that variable is unset and Docker is available.

The database is bootstrapped exactly like production: infra/db/roles.sql, then the Alembic
migrations, then Online Retail II loaded and published through the real refresh
(downloaded to data/ on first use).
Role passwords come from the usual *_PASSWORD variables so a shared dev server keeps working.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "retention_test"
ROLES = ("migrator", "pipeline_rw", "api_ro", "api_ops", "web_auth")
PASSWORD_ENV = {
    "migrator": "MIGRATOR_PASSWORD",
    "pipeline_rw": "PIPELINE_PASSWORD",
    "api_ro": "API_RO_PASSWORD",
    "api_ops": "API_OPS_PASSWORD",
    "web_auth": "WEB_AUTH_PASSWORD",
}


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _with_db(url: str, dbname: str, user: str | None = None, password: str | None = None) -> str:
    u = urlparse(url)
    host = u.netloc.split("@", 1)[-1]
    netloc = f"{user}:{password}@{host}" if user else u.netloc
    return urlunparse(u._replace(netloc=netloc, path=f"/{dbname}"))


def _roles_sql(passwords: dict[str, str]) -> str:
    """infra/db/roles.sql with psql variables substituted (no psql needed)."""
    sql = (ROOT / "infra" / "db" / "roles.sql").read_text(encoding="utf-8")
    sql = "\n".join(line for line in sql.splitlines() if not line.startswith("\\"))
    variables = {
        "migrator_password": "migrator",
        "pipeline_password": "pipeline_rw",
        "api_ro_password": "api_ro",
        "api_ops_password": "api_ops",
        "web_auth_password": "web_auth",
    }
    for var, role in variables.items():
        sql = sql.replace(f":'{var}'", "'" + passwords[role].replace("'", "''") + "'")
    return sql.replace(':"dbname"', f'"{TEST_DB}"')


@pytest.fixture(scope="session")
def admin_url():
    _load_dotenv()
    url = os.environ.get("TEST_ADMIN_DATABASE_URL")
    if url:
        yield url
        return
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("set TEST_ADMIN_DATABASE_URL or install testcontainers")
    try:
        container = PostgresContainer("postgres:16-alpine", driver=None)
        container.start()
    except Exception as e:
        pytest.skip(f"no Postgres available: {e}")
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="session")
def test_db(admin_url):
    """A fresh retention_test database with roles, migrations and env wired to it."""
    passwords = {r: os.environ.get(PASSWORD_ENV[r], "test-password") for r in ROLES}
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'drop database if exists "{TEST_DB}" with (force)')
        conn.execute(f'create database "{TEST_DB}"')
    with psycopg.connect(_with_db(admin_url, TEST_DB), autocommit=True) as conn:
        conn.execute(_roles_sql(passwords))

    urls = {r: _with_db(admin_url, TEST_DB, r, passwords[r]) for r in ROLES}
    os.environ.update(
        {
            "MIGRATOR_DATABASE_URL": urls["migrator"],
            "PIPELINE_DATABASE_URL": urls["pipeline_rw"],
            "API_DATABASE_URL": urls["api_ro"],
            "API_OPS_DATABASE_URL": urls["api_ops"],
            "WEB_DATABASE_URL": urls["web_auth"],
            "PII_KEY": os.environ.get("PII_KEY") or "test0123456789abcdef0123456789",
            "API_JWT_SECRET": os.environ.get("API_JWT_SECRET") or "test-jwt-secret",
            "EXPORT_SIGNING_KEY": os.environ.get("EXPORT_SIGNING_KEY") or "test-export-key",
            "PIPELINE_WEBHOOK_URL": "",
            "APP_ENV": "test",
        }
    )
    if not re.fullmatch(r"[A-Za-z0-9_\-]{16,}", os.environ["PII_KEY"]):
        os.environ["PII_KEY"] = "test0123456789abcdef0123456789"
    from core.config import get_env

    get_env.cache_clear()
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "infra/migrations/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        check=True,
        env=os.environ.copy(),
    )
    with psycopg.connect(urls["pipeline_rw"], autocommit=True) as conn:
        conn.execute(
            "insert into ops.users (email, role, invited_by) values "
            "('admin@example.com', 'admin', 'test'), ('viewer@example.com', 'viewer', 'test') "
            "on conflict do nothing"
        )
    return urls


@pytest.fixture(scope="session")
def published(test_db):
    """Online Retail II (real data), ingested and published through build-audit-publish."""
    from core.db import connect
    from pipeline.ingest.run import load_dataset
    from pipeline.worker.refresh import run_refresh

    with connect() as conn:
        load_dataset(conn, "retail", ROOT / "data")
    result = run_refresh(trigger="seed:test", skip_ingest=True)
    assert result["status"] == "published", result
    return result


@pytest.fixture
def db(published):
    from core.db import connect

    with connect() as conn:
        yield conn
