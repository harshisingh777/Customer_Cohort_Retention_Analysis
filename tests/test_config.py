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


def test_pasted_database_urls_are_cleaned(monkeypatch):
    from core.config import Env

    url = "postgresql://api_ro:pw@ep-x.aws.neon.tech/neondb?sslmode=require"
    for pasted in (
        url,
        f"  {url}\n",
        f"'{url}'",
        f"psql '{url}'",
        f"API_DATABASE_URL={url}",
        f'API_DATABASE_URL="{url}"',
        url.replace("postgresql://", "postgres://"),
    ):
        monkeypatch.setenv("API_DATABASE_URL", pasted)
        assert Env(_env_file=None).api_database_url == url, pasted  # pyright: ignore[reportCallIssue]


def test_cors_origins_tolerate_pasted_values(monkeypatch):
    from core.config import Env

    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "CORS_ALLOWED_ORIGINS=https://a.onrender.com/, http://localhost:3000",
    )
    env = Env(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert env.cors_origins == ["https://a.onrender.com", "http://localhost:3000"]
