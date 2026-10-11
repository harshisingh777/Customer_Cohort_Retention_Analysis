"""Write-audit-publish: a failed or half-finished run never reaches the dashboard."""

import datetime as dt

import psycopg
import pytest

from core.db import connect
from pipeline.worker import refresh

pytestmark = [pytest.mark.db, pytest.mark.slow]


def _version(conn):
    return conn.execute(
        "select version from ops.data_versions order by published_at desc limit 1"
    ).fetchone()["version"]


def _fingerprint(conn):
    return conn.execute(
        "select count(*) as n, sum(active_customers) as a from analytics.mart_cohort_retention_monthly"
    ).fetchone()


def test_failing_test_blocks_publish_and_keeps_yesterdays_data(published):
    with connect() as conn:
        before_version, before = _version(conn), _fingerprint(conn)
    result = refresh.run_refresh(
        trigger="test:canary", skip_ingest=True, extra_vars={"audit_canary": True}
    )
    assert result["status"] == "failed"
    assert "tests failed" in result["error"]
    with connect() as conn:
        assert _version(conn) == before_version
        assert _fingerprint(conn) == before
        run = conn.execute(
            "select status, error, tests from ops.pipeline_runs where id = %s", (result["run_id"],)
        ).fetchone()
        assert run["status"] == "failed"
        assert any("canary" in f["node"] for f in run["tests"]["failures"])


def test_shrink_guard_blocks_publish(published, monkeypatch):
    monkeypatch.setattr(refresh, "SHRINK_TOLERANCE", -1.0)  # every mart now counts as shrunk
    with connect() as conn:
        before_version = _version(conn)
    result = refresh.run_refresh(trigger="test:shrink", skip_ingest=True, allow_shrink=False)
    assert result["status"] == "failed"
    assert "shrank" in result["error"]
    with connect() as conn:
        assert _version(conn) == before_version


def test_reconciliation_guard_blocks_publish(published, monkeypatch):
    monkeypatch.setattr(refresh, "RECONCILIATION_TOLERANCE", -1.0)
    result = refresh.run_refresh(trigger="test:recon", skip_ingest=True)
    assert result["status"] == "failed"
    assert "reconciliation" in result["error"]


def test_successful_refresh_publishes_new_version_and_notifies(published):
    with connect() as conn:
        before = _version(conn)
    listener = psycopg.connect(refresh._dsn(), autocommit=True)
    listener.execute("listen data_published")
    result = refresh.run_refresh(trigger="test:ok", skip_ingest=True)
    assert result["status"] == "published"
    with connect() as conn:
        assert _version(conn) != before
        # Build schemas are gone after a publish; the published one is readable by the API role.
        assert (
            conn.execute("select 1 from pg_namespace where nspname = 'analytics_build'").fetchone()
            is None
        )
    notes = list(listener.notifies(timeout=5, stop_after=1))
    listener.close()
    assert notes and notes[0].payload == result["data_version"]


def test_api_role_cannot_write_or_read_pii(test_db, published):
    with psycopg.connect(test_db["api_ro"]) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select * from pii.customer_contacts limit 1")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("delete from analytics.mart_customer_state")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select * from raw.orders limit 1")
        conn.rollback()
        # Viewers get masked addresses; the API passes reveal only for admins.
        masked = conn.execute("select ops.mask_email('jane.doe@example.com')").fetchone()[0]
        assert masked == "j***@example.com"
        # The function is the API's only path to emails, and it works for api_ro.
        keys = [
            r[0]
            for r in conn.execute("select customer_key from analytics.mart_customer_state limit 50")
        ]
        rows = conn.execute(
            "select email from ops.customer_contacts(%s, false)", (keys,)
        ).fetchall()
        assert all(r[0] is None or "***@" in r[0] for r in rows)


def test_no_raw_email_in_analytics(db):
    cols = db.execute(
        "select table_name, column_name from information_schema.columns "
        "where table_schema = 'analytics' and column_name ilike '%email%' and column_name <> 'email_hmac'"
    ).fetchall()
    assert cols == []


def test_ingest_is_idempotent(published):
    """Re-sending rows already in raw (same source_updated_at) changes nothing."""
    import uuid

    from pipeline.ingest.core import RawRecord, upsert

    with connect() as conn:
        rows = conn.execute(
            "select source, source_id, payload, source_updated_at from raw.orders limit 2000"
        ).fetchall()
        records = [RawRecord(r["source_id"], r["payload"], r["source_updated_at"]) for r in rows]
        rows_in, upserted = upsert(conn, "orders", rows[0]["source"], records, uuid.uuid4())
        conn.commit()
    assert rows_in == len(rows) and upserted == 0


def test_jobs_are_unique_per_schedule_slot(published):
    from pipeline.worker.jobs import claim, enqueue, fail

    slot = dt.datetime(2030, 1, 1, 2, 0, tzinfo=dt.UTC)
    with connect() as conn:
        # Start from an empty queue (earlier tests leave a manual refresh queued).
        conn.execute("update ops.jobs set status = 'succeeded' where status = 'queued'")
        conn.commit()
        first = enqueue(conn, "refresh", {"trigger": "schedule"}, scheduled_for=slot)
        second = enqueue(conn, "refresh", {"trigger": "schedule"}, scheduled_for=slot)
        assert first is not None and second is None
        job = claim(conn, "test-worker")
        assert job is not None and job.id == first
        assert claim(conn, "other-worker") is None  # SKIP LOCKED: nothing else queued
        fail(conn, job, "boom")
        row = conn.execute(
            "select status, run_after > now() as later from ops.jobs where id = %s", (first,)
        ).fetchone()
        assert row["status"] == "queued" and row["later"]  # retried with backoff
        conn.execute("delete from ops.jobs where id = %s", (first,))
        conn.commit()
