"""The refresh job: ingest → build → audit → publish-or-nothing (spec §9.3).

A failed or half-finished run never reaches the dashboard: dbt builds into analytics_build
(and pii_build), the audit must pass, and only then are the schemas swapped in one
transaction. On any failure the published `analytics` schema is untouched and the run row
says why, so the Data page can show "stale since".
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import sql

from core.db import Conn, connect, read_store_settings
from pipeline.ingest.run import ingest_live
from pipeline.worker import notify
from pipeline.worker.dbt_runner import run_dbt

log = logging.getLogger(__name__)

LOCK_KEY = "refresh"
RECONCILIATION_TOLERANCE = 0.005  # 0.5%
SHRINK_TOLERANCE = 0.20  # 20%
SWAPPED_SCHEMAS = ("analytics", "pii")


class AuditFailed(Exception):
    pass


@contextmanager
def advisory_lock(wait_seconds: int = 1800):
    """Session-level lock on a dedicated connection; released when the block exits."""
    conn = psycopg.connect(_dsn(), autocommit=True)
    try:
        deadline = time.monotonic() + wait_seconds
        while True:
            got = conn.execute("select pg_try_advisory_lock(hashtext(%s))", (LOCK_KEY,)).fetchone()
            if got and got[0]:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("another refresh held the lock for too long")
            time.sleep(10)
        yield
    finally:
        try:
            conn.execute("select pg_advisory_unlock(hashtext(%s))", (LOCK_KEY,))
        finally:
            conn.close()


def _dsn() -> str:
    from core.db import pipeline_dsn

    return pipeline_dsn()


class Run:
    """Records each step's duration and outcome into ops.pipeline_runs as it goes."""

    def __init__(self, conn: Conn, kind: str, trigger: str, job_id: int | None) -> None:
        self.conn = conn
        row = conn.execute(
            "insert into ops.pipeline_runs (job_id, kind, trigger, status) values (%s, %s, %s, 'running') returning id",
            (job_id, kind, trigger),
        ).fetchone()
        conn.commit()
        self.id: int = row["id"]  # type: ignore[index]
        self.steps: list[dict] = []
        self.started = time.monotonic()

    def step(self, name: str, fn: Callable[[], Any]) -> Any:
        t0 = time.monotonic()
        try:
            out = fn()
            self.steps.append(
                {"name": name, "status": "ok", "seconds": round(time.monotonic() - t0, 2)}
            )
            return out
        except Exception as e:
            self.steps.append(
                {
                    "name": name,
                    "status": "failed",
                    "seconds": round(time.monotonic() - t0, 2),
                    "error": str(e)[:500],
                }
            )
            raise
        finally:
            self.conn.execute(
                "update ops.pipeline_runs set steps = %s where id = %s",
                (json.dumps(self.steps), self.id),
            )
            self.conn.commit()

    def update(self, **fields: Any) -> None:
        self._write(None, fields)

    def finish(self, status: str, **fields: Any) -> None:
        self._write(status, fields)

    def _write(self, status: str | None, fields: dict[str, Any]) -> None:
        sets: list[sql.Composable] = [sql.SQL("steps = %s")]
        values: list[Any] = [json.dumps(self.steps)]
        if status:
            sets += [sql.SQL("status = %s"), sql.SQL("finished_at = now()")]
            values.append(status)
        for k, v in fields.items():
            sets.append(sql.SQL("{} = %s").format(sql.Identifier(k)))
            values.append(json.dumps(v, default=str) if isinstance(v, dict | list) else v)
        self.conn.execute(
            sql.SQL("update ops.pipeline_runs set {} where id = %s").format(
                sql.SQL(", ").join(sets)
            ),
            [*values, self.id],
        )
        self.conn.commit()


def _schema_exists(conn: Conn, name: str) -> bool:
    return (
        conn.execute("select 1 from pg_namespace where nspname = %s", (name,)).fetchone()
        is not None
    )


def _drop_build_schemas(conn: Conn) -> None:
    for s in SWAPPED_SCHEMAS:
        conn.execute(
            sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(f"{s}_build"))
        )
    conn.commit()


def _mart_counts(conn: Conn, schema: str) -> dict[str, int]:
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = %s and table_name like 'mart\\_%%'",
        (schema,),
    ).fetchall()
    out = {}
    for r in rows:
        t = r["table_name"]
        row = conn.execute(
            sql.SQL("select count(*) as n from {}").format(sql.Identifier(schema, t))
        ).fetchone()
        out[t] = row["n"] if row else 0
    return out


def audit(conn: Conn, dbt_ok: bool, allow_shrink: bool) -> tuple[dict, dict]:
    """Every check must pass. Returns (reconciliation, row_counts) for the run record."""
    if not dbt_ok:
        raise AuditFailed("dbt build or tests failed")

    dq = conn.execute("select cutoff_date from analytics_build.mart_data_quality").fetchone()
    if dq is None:
        raise AuditFailed("mart_data_quality is empty")
    cutoff: dt.date = dq["cutoff_date"]
    rec = conn.execute(
        """
        select coalesce(sum(source_revenue), 0)::float as source_revenue,
               coalesce(sum(mart_revenue), 0)::float as mart_revenue,
               coalesce(sum(source_orders), 0)::int as source_orders,
               coalesce(sum(mart_orders), 0)::int as mart_orders,
               coalesce(sum(unidentified_revenue), 0)::float as unidentified_revenue
        from analytics_build.mart_reconciliation
        where day >= %s::date - 90 and day < %s::date
        """,
        (cutoff, cutoff),
    ).fetchone()
    if rec is None:
        raise AuditFailed("mart_reconciliation is missing")
    src, mart = rec["source_revenue"], rec["mart_revenue"]
    delta_pct = abs(mart - src) / src if src else 0.0
    reconciliation = {
        **rec,
        "window_days": 90,
        "delta_pct": round(delta_pct, 6),
        "tolerance": RECONCILIATION_TOLERANCE,
        "passed": delta_pct <= RECONCILIATION_TOLERANCE,
    }
    if not reconciliation["passed"]:
        raise AuditFailed(
            f"reconciliation off by {delta_pct:.2%} over the last 90 days (limit 0.5%)"
        )

    new_counts = _mart_counts(conn, "analytics_build")
    old_counts = _mart_counts(conn, "analytics") if _schema_exists(conn, "analytics") else {}
    shrunk = {
        t: {"before": old_counts[t], "after": n}
        for t, n in new_counts.items()
        if old_counts.get(t, 0) > 0 and n < old_counts[t] * (1 - SHRINK_TOLERANCE)
    }
    row_counts = {"marts": new_counts, "shrunk": shrunk, "override": allow_shrink}
    if shrunk and not allow_shrink:
        raise AuditFailed(f"marts shrank by more than 20%: {', '.join(sorted(shrunk))}")
    return reconciliation, row_counts


def publish(conn: Conn, run_id: int) -> tuple[str, dt.date]:
    """Grant, then swap analytics_build → analytics (and pii) in one transaction."""
    conn.execute("grant usage on schema analytics_build to api_ro")
    conn.execute("grant select on all tables in schema analytics_build to api_ro")
    conn.commit()
    dq = conn.execute("select data_through from analytics_build.mart_data_quality").fetchone()
    if dq is None:
        raise AuditFailed("mart_data_quality is empty")
    data_through: dt.date = dq["data_through"]

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with conn.transaction():
                conn.execute("set local lock_timeout = '5s'")
                for s in SWAPPED_SCHEMAS:
                    if _schema_exists(conn, s):
                        conn.execute(
                            sql.SQL("alter schema {} rename to {}").format(
                                sql.Identifier(s), sql.Identifier(f"{s}_prev")
                            )
                        )
                    conn.execute(
                        sql.SQL("alter schema {} rename to {}").format(
                            sql.Identifier(f"{s}_build"), sql.Identifier(s)
                        )
                    )
                for s in SWAPPED_SCHEMAS:
                    conn.execute(
                        sql.SQL("drop schema if exists {} cascade").format(
                            sql.Identifier(f"{s}_prev")
                        )
                    )
                now = conn.execute("select now() as t").fetchone()
                published: dt.datetime = now["t"] if now else dt.datetime.now(dt.UTC)
                version = f"{published.astimezone(dt.UTC):%Y-%m-%dT%H:%M:%SZ}/{run_id}"
                conn.execute(
                    "insert into ops.data_versions (version, run_id, data_through, published_at) values (%s, %s, %s, %s)",
                    (version, run_id, data_through, published),
                )
                conn.execute("select pg_notify('data_published', %s)", (version,))
            return version, data_through
        except psycopg.errors.LockNotAvailable as e:
            last_error = e
            conn.rollback()
            time.sleep(2 ** (attempt + 1))
    raise AuditFailed(f"publish could not take the schema lock after 3 attempts: {last_error}")


def run_refresh(
    *,
    trigger: str,
    job_id: int | None = None,
    skip_ingest: bool = False,
    allow_shrink: bool | None = None,
    extra_vars: dict | None = None,
) -> dict:
    # A seed replaces the whole dataset, so shrinking marts are expected there.
    allow_shrink = trigger.startswith("seed") if allow_shrink is None else allow_shrink
    with advisory_lock(), connect() as conn:
        run = Run(conn, "refresh", trigger, job_id)
        try:
            settings = read_store_settings(conn)
            ingest_stats = {} if skip_ingest else run.step("ingest", lambda: ingest_live(conn))
            run.step("prepare", lambda: _drop_build_schemas(conn))
            dbt = run.step(
                "build", lambda: run_dbt("build", {**settings.dbt_vars(), **(extra_vars or {})})
            )
            run.update(tests=dbt.as_json())
            try:
                reconciliation, row_counts = run.step(
                    "audit", lambda: audit(conn, dbt.ok, allow_shrink)
                )
            except AuditFailed:
                if not dbt.ok:
                    log.error(
                        "dbt failed", extra={"failures": dbt.failures, "log": dbt.log_tail[-2000:]}
                    )
                raise
            version, data_through = run.step("publish", lambda: publish(conn, run.id))
            run.finish(
                "published",
                data_version=version,
                reconciliation=reconciliation,
                row_counts=row_counts,
            )
            elapsed = time.monotonic() - run.started
            notify.post(
                f"Refresh published: data through {data_through:%d %b %Y} ({elapsed:.0f}s, run {run.id})."
            )
            return {
                "status": "published",
                "run_id": run.id,
                "data_version": version,
                "data_through": data_through,
                "ingest": ingest_stats,
                "tests": dbt.as_json(),
                "reconciliation": reconciliation,
            }
        except Exception as e:
            conn.rollback()
            msg = str(e) if isinstance(e, AuditFailed) else f"{type(e).__name__}: {e}"
            run.finish("failed", error=msg[:4000])
            log.error(
                "refresh failed",
                extra={"run_id": run.id, "error": msg, "trace": traceback.format_exc()[-3000:]},
            )
            notify.post(
                f"Refresh FAILED (run {run.id}): {msg[:300]}. The dashboard still shows the previous data."
            )
            # The failed build is left in *_build for inspection; the next run drops it first.
            return {"status": "failed", "run_id": run.id, "error": msg}
