"""ops.jobs: a Postgres-backed queue. Claimed with FOR UPDATE SKIP LOCKED, retried with
exponential backoff up to max_attempts, pruned after 30 days. No Redis, no Celery."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any

from core.db import Conn

STALE_AFTER = dt.timedelta(hours=2)


@dataclass
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    created_by: str | None


def enqueue(
    conn: Conn,
    kind: str,
    payload: dict | None = None,
    *,
    scheduled_for: dt.datetime | None = None,
    created_by: str = "system",
) -> int | None:
    """Insert a job. A (kind, scheduled_for) duplicate is ignored and returns None."""
    row = conn.execute(
        """
        insert into ops.jobs (kind, payload, scheduled_for, run_after, created_by)
        values (%s, %s, coalesce(%s, now()), now(), %s)
        on conflict (kind, scheduled_for) do nothing
        returning id
        """,
        (kind, json.dumps(payload or {}), scheduled_for, created_by),
    ).fetchone()
    conn.commit()
    return row["id"] if row else None  # type: ignore[index]


def claim(conn: Conn, worker_id: str) -> Job | None:
    row = conn.execute(
        """
        update ops.jobs
           set status = 'running', locked_at = now(), locked_by = %s, attempts = attempts + 1
         where id = (
           select id from ops.jobs
            where status = 'queued' and run_after <= now()
            order by run_after, id
            for update skip locked
            limit 1
         )
        returning id, kind, payload, attempts, max_attempts, created_by
        """,
        (worker_id,),
    ).fetchone()
    conn.commit()
    if not row:
        return None
    return Job(
        row["id"],
        row["kind"],
        row["payload"],
        row["attempts"],
        row["max_attempts"],
        row["created_by"],
    )  # type: ignore[index]


def succeed(conn: Conn, job: Job) -> None:
    conn.execute(
        "update ops.jobs set status = 'succeeded', finished_at = now(), error = null where id = %s",
        (job.id,),
    )
    conn.commit()


def fail(conn: Conn, job: Job, error: str, *, retry: bool = True) -> None:
    if retry and job.attempts < job.max_attempts:
        backoff = dt.timedelta(minutes=2**job.attempts)
        conn.execute(
            "update ops.jobs set status = 'queued', run_after = now() + %s, error = %s, "
            "locked_at = null, locked_by = null where id = %s",
            (backoff, error[:4000], job.id),
        )
    else:
        conn.execute(
            "update ops.jobs set status = 'failed', finished_at = now(), error = %s where id = %s",
            (error[:4000], job.id),
        )
    conn.commit()


def requeue_stale(conn: Conn) -> int:
    """Jobs left 'running' by a worker that died."""
    cur = conn.execute(
        "update ops.jobs set status = 'queued', locked_at = null, locked_by = null "
        "where status = 'running' and locked_at < now() - %s",
        (STALE_AFTER,),
    )
    conn.commit()
    return cur.rowcount


def prune(conn: Conn) -> int:
    cur = conn.execute(
        "delete from ops.jobs where status in ('succeeded', 'failed') and finished_at < now() - interval '30 days'"
    )
    conn.commit()
    return cur.rowcount
