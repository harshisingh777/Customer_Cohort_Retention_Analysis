"""Set up a hosted Postgres (e.g. Neon) for a presentation deployment, from scratch or again.

Runs what production does once by hand: infra/db/roles.sql, the Alembic migrations, the demo
users, then Online Retail II through the real ingest, refresh and publish (and the CLV fit).
Idempotent: re-running reloads the data.

Environment:
  DEMO_ADMIN_DATABASE_URL  the database owner's URL (Neon: the default role, direct connection)
  DEMO_ROLE_PASSWORD       password for the five app roles (migrator, pipeline_rw, api_ro, ...)
  PII_KEY                  16+ characters of [A-Za-z0-9_-]

  python scripts/demo_db.py [--skip-clv]
  python scripts/demo_db.py --print-env   the Render values for the database URLs; changes nothing
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import LiteralString, cast
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg

ROOT = Path(__file__).resolve().parents[1]
ROLES = {
    "migrator": "MIGRATOR_DATABASE_URL",
    "pipeline_rw": "PIPELINE_DATABASE_URL",
    "api_ro": "API_DATABASE_URL",
    "api_ops": "API_OPS_DATABASE_URL",
    "web_auth": "WEB_DATABASE_URL",
}
DEMO_USERS = [("admin@example.com", "admin"), ("viewer@example.com", "viewer")]


def role_url(admin_url: str, role: str, password: str) -> str:
    u = urlsplit(admin_url)
    host = u.netloc.split("@", 1)[-1]
    return urlunsplit(u._replace(netloc=f"{role}:{quote(password, safe='')}@{host}"))


def roles_sql(dbname: str, password: str) -> str:
    """infra/db/roles.sql with its psql variables substituted (no psql needed)."""
    sql = (ROOT / "infra" / "db" / "roles.sql").read_text(encoding="utf-8")
    sql = "\n".join(line for line in sql.splitlines() if not line.startswith("\\"))
    for var in ("migrator", "pipeline", "api_ro", "api_ops", "web_auth"):
        sql = sql.replace(f":'{var}_password'", "'" + password.replace("'", "''") + "'")
    return sql.replace(':"dbname"', '"' + dbname.replace('"', '""') + '"')


def run(*args: str) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True, env=os.environ.copy())  # noqa: S603


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--skip-clv", action="store_true", help="skip the CLV model fit")
    ap.add_argument("--print-env", action="store_true", help="print the app's database URLs")
    args = ap.parse_args()

    admin_url = os.environ["DEMO_ADMIN_DATABASE_URL"]
    password = os.environ["DEMO_ROLE_PASSWORD"]
    dbname = urlsplit(admin_url).path.lstrip("/")

    if args.print_env:
        for role in ("api_ro", "api_ops", "web_auth"):
            print(f"{ROLES[role]}={role_url(admin_url, role, password)}")
        return 0

    print(f"roles in database {dbname}", flush=True)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(cast(LiteralString, roles_sql(dbname, password)))

    os.environ.update({var: role_url(admin_url, role, password) for role, var in ROLES.items()})
    os.environ.setdefault("APP_ENV", "demo")
    run("-m", "alembic", "-c", "infra/migrations/alembic.ini", "upgrade", "head")

    with psycopg.connect(os.environ["PIPELINE_DATABASE_URL"], autocommit=True) as conn:
        for email, role in DEMO_USERS:
            conn.execute(
                "insert into ops.users (email, role, invited_by) values (%s, %s, 'demo') "
                "on conflict do nothing",
                (email, role),
            )

    run("-m", "pipeline.ingest", "seed", "retail", *(["--skip-clv"] if args.skip_clv else []))

    with psycopg.connect(admin_url) as conn:
        size = conn.execute(
            "select pg_size_pretty(pg_database_size(current_database()))"
        ).fetchone()
        print(f"database size: {size[0] if size else '?'}")
        for schema, total in conn.execute(
            "select table_schema, pg_size_pretty(sum(pg_total_relation_size("
            "quote_ident(table_schema) || '.' || quote_ident(table_name)))::bigint) "
            "from information_schema.tables "
            "where table_schema not in ('pg_catalog', 'information_schema') "
            "group by table_schema order by sum(pg_total_relation_size("
            "quote_ident(table_schema) || '.' || quote_ident(table_name))) desc"
        ):
            print(f"  {schema}: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
