"""The worker: claims jobs from ops.jobs and runs the internal schedule.

python -m pipeline.worker            run forever
python -m pipeline.worker refresh    one refresh now, in the foreground
python -m pipeline.worker clv        one CLV fit now
"""

from __future__ import annotations

import logging
import signal
import socket
import sys
import time
import traceback

from core.config import get_env
from core.db import connect
from core.logging import init_sentry, setup_logging
from pipeline.worker import jobs
from pipeline.worker.scheduler import schedule_due

log = logging.getLogger("worker")
_stop = False


def _handle_stop(*_: object) -> None:
    global _stop
    _stop = True


def bootstrap_admin() -> None:
    email = get_env().bootstrap_admin_email.strip().lower()
    if not email:
        return
    with connect() as conn:
        exists = conn.execute("select 1 from ops.users limit 1").fetchone()
        if not exists:
            conn.execute(
                "insert into ops.users (email, role, invited_by) values (%s, 'admin', 'bootstrap') "
                "on conflict do nothing",
                (email,),
            )
            conn.execute(
                "insert into ops.audit_log (actor, action, detail) values ('bootstrap', 'user.invite', "
                "jsonb_build_object('email', %s::text, 'role', 'admin'))",
                (email,),
            )
            conn.commit()
            log.info("bootstrap admin created", extra={"email": email})


def run_job(job: jobs.Job) -> None:
    if job.kind == "refresh":
        from pipeline.worker.refresh import run_refresh

        result = run_refresh(
            trigger=job.payload.get("trigger", job.created_by or "manual"),
            job_id=job.id,
            allow_shrink=bool(job.payload.get("allow_shrink", False)),
        )
        if result["status"] != "published":
            # The run is recorded; don't retry an audit failure blindly.
            raise RuntimeError(result.get("error", "refresh failed"))
    elif job.kind == "clv_fit":
        from pipeline.clv.fit import run_clv_fit

        run_clv_fit(trigger=job.payload.get("trigger", "manual"), job_id=job.id)
    elif job.kind == "pdf_export":
        from pipeline.worker.pdf_export import run_pdf_export

        with connect() as conn:
            run_pdf_export(conn, job.payload["export_id"])
    else:
        raise ValueError(f"unknown job kind {job.kind!r}")


def loop() -> None:
    env = get_env()
    worker_id = f"{socket.gethostname()}:{id(object())}"
    bootstrap_admin()
    last_schedule = 0.0
    last_prune = 0.0
    log.info("worker started", extra={"worker_id": worker_id})
    while not _stop:
        try:
            with connect() as conn:
                now = time.monotonic()
                if now - last_schedule > 60:
                    jobs.requeue_stale(conn)
                    created = schedule_due(conn)
                    if created:
                        log.info("scheduled jobs", extra={"job_ids": created})
                    last_schedule = now
                if now - last_prune > 3600:
                    jobs.prune(conn)
                    last_prune = now
                job = jobs.claim(conn, worker_id)
            if job is None:
                time.sleep(env.worker_poll_seconds)
                continue
            log.info(
                "job started", extra={"job_id": job.id, "kind": job.kind, "attempt": job.attempts}
            )
            t0 = time.monotonic()
            try:
                run_job(job)
                with connect() as conn:
                    jobs.succeed(conn, job)
                log.info(
                    "job succeeded",
                    extra={"job_id": job.id, "seconds": round(time.monotonic() - t0, 1)},
                )
            except Exception as e:
                # Audit failures are deterministic: retrying the same data won't help.
                retry = job.kind != "refresh"
                with connect() as conn:
                    jobs.fail(
                        conn,
                        job,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}",
                        retry=retry,
                    )
                log.error("job failed", extra={"job_id": job.id, "kind": job.kind, "error": str(e)})
        except Exception:
            log.exception("worker loop error")
            time.sleep(5)


def main(argv: list[str]) -> int:
    setup_logging()
    env = get_env()
    init_sentry(env.sentry_dsn, env.git_sha, env.app_env)
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    if argv and argv[0] == "refresh":
        from pipeline.worker.refresh import run_refresh

        result = run_refresh(trigger="cli", allow_shrink="--allow-shrink" in argv)
        print(result)
        return 0 if result["status"] == "published" else 1
    if argv and argv[0] == "dbt":
        # Developer passthrough with the worker's connection, PII session key and current vars.
        import json
        import subprocess

        from core.db import connect, read_store_settings
        from pipeline.worker.dbt_runner import DBT_DIR, dbt_env

        with connect() as conn:
            dbt_vars = read_store_settings(conn).dbt_vars()
        cmd = [
            "dbt",
            *argv[1:],
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--vars",
            json.dumps(dbt_vars),
        ]
        return subprocess.call(cmd, env=dbt_env())  # noqa: S603
    if argv and argv[0] == "clv":
        from pipeline.clv.fit import run_clv_fit

        print(run_clv_fit(trigger="cli"))
        return 0
    loop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
