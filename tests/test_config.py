"""Connection-string handling for hosted Postgres (Neon-style URLs)."""

from core.config import to_asyncpg_dsn, to_asyncpg_url, to_psycopg_url

NEON = "postgresql://api_ro:pw@ep-x.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


def test_psycopg_keeps_libpq_parameters():
    assert to_psycopg_url(NEON) == NEON


def test_asyncpg_dsn_drops_libpq_only_parameters():
    assert (
        to_asyncpg_dsn(NEON) == "postgresql://api_ro:pw@ep-x.aws.neon.tech/neondb?sslmode=require"
    )


def test_asyncpg_url_uses_ssl_for_sqlalchemy():
    assert (
        to_asyncpg_url(NEON)
        == "postgresql+asyncpg://api_ro:pw@ep-x.aws.neon.tech/neondb?ssl=require"
    )


def test_plain_local_urls_are_unchanged():
    assert to_asyncpg_url("postgresql://u:p@db:5432/retention") == (
        "postgresql+asyncpg://u:p@db:5432/retention"
    )
    assert to_asyncpg_url("postgresql+psycopg://u:p@db/retention") == (
        "postgresql+asyncpg://u:p@db/retention"
    )
