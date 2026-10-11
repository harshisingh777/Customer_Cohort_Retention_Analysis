"""Environment configuration. Every environment-specific value comes from here."""

import re
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    git_sha: str = "local"

    migrator_database_url: str = ""
    pipeline_database_url: str = ""
    api_database_url: str = ""
    api_ops_database_url: str = ""

    @field_validator(
        "migrator_database_url",
        "pipeline_database_url",
        "api_database_url",
        "api_ops_database_url",
        mode="before",
    )
    @classmethod
    def _clean_database_url(cls, value: object) -> object:
        return clean_database_url(value) if isinstance(value, str) else value

    pii_key: str = ""
    api_jwt_secret: str = ""
    export_signing_key: str = ""
    bootstrap_admin_email: str = ""

    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_allowed_origins: str = "http://localhost:3000"

    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = ""

    sentry_dsn: str = ""
    pipeline_webhook_url: str = ""

    shopify_shop: str = ""
    shopify_access_token: str = ""
    woo_base_url: str = ""
    woo_consumer_key: str = ""
    woo_consumer_secret: str = ""

    # Worker tuning
    worker_poll_seconds: float = 3.0
    data_dir: str = Field(
        default="data", description="Where public datasets are cached for seeding"
    )

    @property
    def cors_origins(self) -> list[str]:
        # Browsers send origins without a trailing slash; pasted dashboard values often have one.
        origins = clean_database_url(self.cors_allowed_origins).split(",")
        return [o.strip().strip("'\"").rstrip("/") for o in origins if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_env() -> Env:
    return Env()


_LIBPQ_ONLY = {"channel_binding"}
_PASTED_PREFIX = re.compile(r"^(?:psql\s+|[A-Z][A-Z0-9_]*=)")


def clean_database_url(value: str) -> str:
    """Undo common copy-paste wrapping of a connection string in a dashboard: surrounding
    whitespace and quotes, Neon's `psql '...'` form, or a whole `NAME=value` line."""
    value = value.strip()
    while (prefix := _PASTED_PREFIX.match(value)) is not None:
        value = value[prefix.end() :].strip()
    value = value.strip("'\"").strip()
    return "postgresql://" + value[11:] if value.startswith("postgres://") else value


def to_psycopg_url(url: str) -> str:
    """Normalise a SQLAlchemy-style URL to a libpq one."""
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


def to_asyncpg_dsn(url: str) -> str:
    """A libpq URL asyncpg accepts. asyncpg sends unknown query parameters as server settings,
    so libpq-only ones that hosted Postgres URLs carry (Neon: channel_binding) are dropped."""
    parts = urlsplit(to_psycopg_url(url))
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in _LIBPQ_ONLY]
    return urlunsplit(parts._replace(query=urlencode(query)))


def to_asyncpg_url(url: str) -> str:
    """SQLAlchemy's asyncpg dialect passes query parameters to asyncpg.connect, which takes
    ssl= rather than libpq's sslmode=."""
    parts = urlsplit(to_asyncpg_dsn(url))
    query = [("ssl" if k == "sslmode" else k, v) for k, v in parse_qsl(parts.query)]
    return urlunsplit(parts._replace(scheme="postgresql+asyncpg", query=urlencode(query)))
