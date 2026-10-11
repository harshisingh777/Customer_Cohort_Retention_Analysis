from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select

from apps.api.auth import AdminUser
from apps.api.db import db
from apps.api.errors import not_found
from apps.api.schemas import JobOut, RunOut, RunRequested
from apps.api.tables import audit_t, jobs_t, runs_t

router = APIRouter(prefix="/v1/pipeline", tags=["pipeline"])


@router.post(
    "/runs",
    response_model=RunRequested,
    status_code=202,
    summary="Enqueue a manual refresh. If one is already queued or running, returns it.",
)
async def request_run(user: AdminUser):
    async with db.ops.begin() as conn:
        existing = (
            await conn.execute(
                select(jobs_t.c.id, jobs_t.c.status)
                .where(jobs_t.c.kind == "refresh", jobs_t.c.status.in_(["queued", "running"]))
                .order_by(jobs_t.c.id.desc())
                .limit(1)
            )
        ).first()
        if existing:
            return JSONResponse(
                RunRequested(
                    job_id=existing.id, status=existing.status, existing=True
                ).model_dump(),
                status_code=200,
            )
        job_id = (
            await conn.execute(
                insert(jobs_t)
                .values(kind="refresh", payload={"trigger": "manual"}, created_by=user.email)
                .returning(jobs_t.c.id)
            )
        ).scalar_one()
        await conn.execute(
            insert(audit_t).values(
                actor=user.email, action="pipeline.refresh", detail={"job_id": job_id}
            )
        )
    return RunRequested(job_id=job_id, status="queued", existing=False)


@router.get("/runs/{job_id}", response_model=JobOut, summary="Status of a refresh job and its run")
async def run_status(user: AdminUser, job_id: Annotated[int, Path(ge=1)]) -> JobOut:
    async with db.ro.connect() as conn:
        job = (await conn.execute(select(jobs_t).where(jobs_t.c.id == job_id))).first()
        if job is None:
            raise not_found("This refresh job")
        run = (
            await conn.execute(
                select(runs_t)
                .where(runs_t.c.job_id == job_id)
                .order_by(runs_t.c.started_at.desc())
                .limit(1)
            )
        ).first()
    return JobOut(
        job_id=job.id,
        kind=job.kind,
        status=job.status,
        attempts=job.attempts,
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
        run=RunOut(
            id=run.id,
            status=run.status,
            trigger=run.trigger,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error=run.error,
            duration_s=(run.finished_at - run.started_at).total_seconds()
            if run.finished_at
            else None,
            steps=run.steps or [],
            tests=run.tests,
            reconciliation=run.reconciliation,
            data_version=run.data_version,
        )
        if run
        else None,
    )
