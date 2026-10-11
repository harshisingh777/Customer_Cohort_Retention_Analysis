from __future__ import annotations

import datetime as dt
from typing import cast

from fastapi import APIRouter, Request
from sqlalchemy import select

from apps.api.auth import CurrentUser
from apps.api.cache import uncached
from apps.api.db import db
from apps.api.filters import strict
from apps.api.schemas import DataHealth, ReconDay, RunOut
from apps.api.services.store import CLV_MAPE_LIMIT, clv_status, freshness
from apps.api.tables import batches_t, clv_model, data_quality, reconciliation, runs_t

router = APIRouter(prefix="/v1", tags=["data"])


def _num(v):
    if v is None:
        return None
    if isinstance(v, int | float | str | bool | dt.date):
        return v
    return float(v)


@router.get(
    "/data-health",
    response_model=DataHealth,
    dependencies=[strict()],
    summary="Runs, freshness, tests, reconciliation, identity merge rate, dropped rows, CLV holdout",
)
async def data_health(request: Request, user: CurrentUser):
    v = db.current
    async with db.ro.connect() as conn:
        fresh = await freshness(conn)
        runs = (
            await conn.execute(select(runs_t).order_by(runs_t.c.started_at.desc()).limit(30))
        ).all()
        quality = recon_daily = recon = clv = None
        if v is not None:
            row = (await conn.execute(select(data_quality))).first()
            quality = {k: _num(val) for k, val in row._mapping.items()} if row else None
            cutoff = (
                cast(dt.date, quality["cutoff_date"])
                if quality
                else v.data_through + dt.timedelta(days=1)
            )
            rows = (
                await conn.execute(
                    select(reconciliation)
                    .where(reconciliation.c.day >= cutoff - dt.timedelta(days=90))
                    .order_by(reconciliation.c.day)
                )
            ).all()
            recon_daily = [
                ReconDay(
                    day=r.day,
                    source_revenue=float(r.source_revenue),
                    mart_revenue=float(r.mart_revenue),
                    delta=float(r.delta),
                )
                for r in rows
            ]
            src = sum(r.source_revenue for r in recon_daily)
            mart = sum(r.mart_revenue for r in recon_daily)
            recon = {
                "window_days": 90,
                "source_revenue": src,
                "mart_revenue": mart,
                "unidentified_revenue": float(sum(r.unidentified_revenue for r in rows)),
                "delta_pct": abs(mart - src) / src if src else 0.0,
                "tolerance": 0.005,
            }
            has_model, visible, reason, mape = await clv_status(conn)
            if has_model:
                cohorts = (
                    await conn.execute(select(clv_model).order_by(clv_model.c.cohort_month))
                ).all()
                head = cohorts[0] if cohorts else None
                clv = {
                    "model_version": head.model_version if head else None,
                    "fitted_at": head.fitted_at if head else None,
                    "method": head.method if head else None,
                    "holdout_days": head.holdout_days if head else None,
                    "holdout_mape": mape,
                    "limit": CLV_MAPE_LIMIT,
                    "visible": visible,
                    "hidden_reason": reason,
                    "cohorts": [
                        {
                            "cohort_month": c.cohort_month,
                            "customers": c.customers,
                            "predicted": float(c.predicted_revenue),
                            "actual": float(c.actual_revenue),
                        }
                        for c in cohorts
                        if c.cohort_month is not None
                    ],
                }
        batches = (
            await conn.execute(select(batches_t).order_by(batches_t.c.started_at.desc()).limit(40))
        ).all()
    payload = DataHealth(
        freshness=fresh,
        data_version=v.version if v else None,
        data_through=v.data_through if v else None,
        published_at=v.published_at if v else None,
        runs=[
            RunOut(
                id=r.id,
                status=r.status,
                trigger=r.trigger,
                started_at=r.started_at,
                finished_at=r.finished_at,
                error=r.error,
                duration_s=(r.finished_at - r.started_at).total_seconds()
                if r.finished_at
                else None,
                steps=r.steps or [],
                tests=r.tests,
                reconciliation=r.reconciliation,
                data_version=r.data_version,
            )
            for r in runs
        ],
        reconciliation_daily=recon_daily or [],
        reconciliation=recon,
        quality=quality,
        ingest=[
            {
                "source": b.source,
                "entity": b.entity,
                "finished_at": b.finished_at,
                "rows_in": b.rows_in,
                "rows_upserted": b.rows_upserted,
                "rows_dropped": b.rows_dropped,
                "drop_reasons": b.drop_reasons,
            }
            for b in batches
        ],
        clv=clv,
    )
    return await uncached(request, payload, v)
