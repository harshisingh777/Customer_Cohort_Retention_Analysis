"""Synchronous Postgres access for the worker, ingest and CLV jobs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import DictRow, dict_row

from core.config import get_env, to_psycopg_url
from core.store_settings import StoreSettings, load_store_settings

# Every pipeline connection returns rows as dicts.
Conn = psycopg.Connection[DictRow]


def pipeline_dsn() -> str:
    return to_psycopg_url(get_env().pipeline_database_url)


@contextmanager
def connect(dsn: str | None = None, *, autocommit: bool = False) -> Iterator[Conn]:
    conn = psycopg.Connection[DictRow].connect(
        dsn or pipeline_dsn(), autocommit=autocommit, row_factory=dict_row
    )
    try:
        yield conn
    finally:
        conn.close()


def read_store_settings(conn: Conn) -> StoreSettings:
    rows = conn.execute("select key, value from ops.settings").fetchall()
    return load_store_settings([(r["key"], r["value"]) for r in rows])
