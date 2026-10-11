"""Store settings, freshness and CLV visibility, shared by several routes."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from apps.api.db import db
from apps.api.schemas import Freshness, RunBrief
from apps.api.tables import clv_model, runs_t, settings_t
from core.store_settings import StoreSettings, load_store_settings

CLV_MAPE_LIMIT = 0.30


async def read_settings(conn: AsyncConnection) -> StoreSettings:
    rows = (await conn.execute(select(settings_t.c.key, settings_t.c.value))).all()
    return load_store_settings([(r.key, r.value) for r in rows])


async def freshness(conn: AsyncConnection) -> Freshness:
    row = (
        await conn.execute(
            select(
                runs_t.c.id,
                runs_t.c.status,
                runs_t.c.trigger,
                runs_t.c.started_at,
                runs_t.c.finished_at,
                runs_t.c.error,
            )
            .where(runs_t.c.kind == "refresh", runs_t.c.status != "running")
            .order_by(runs_t.c.started_at.desc())
            .limit(1)
        )
    ).first()
    last = RunBrief(**row._mapping) if row else None
    current = db.current
    if current is None:
        msg = "No data has been published yet."
        if last and last.status == "failed":
            msg = "The first refresh failed. Details on the Data page."
        return Freshness(state="empty", message=msg, last_run=last)
    if last and last.status == "failed" and last.started_at > current.published_at:
        when = "Last night's" if last.trigger == "schedule" else "The latest"
        return Freshness(
            state="stale",
            message=(
                f"{when} refresh failed. Showing data through "
                f"{current.data_through.day} {current.data_through:%b %Y}. Details on the Data page."
            ),
            last_run=last,
        )
    return Freshness(state="fresh", message=None, last_run=last)


async def clv_status(conn: AsyncConnection) -> tuple[bool, bool, str | None, float | None]:
    """(has_model, visible, hidden_reason, mape)."""
    row = (
        await conn.execute(
            select(clv_model.c.model_version, func.max(clv_model.c.holdout_mape).label("mape"))
            .group_by(clv_model.c.model_version)
            .limit(1)
        )
    ).first()
    if not row or row.model_version is None:
        return False, False, "Predicted LTV appears after the first weekly model fit.", None
    mape = float(row.mape) if row.mape is not None else None
    if mape is None:
        return (
            True,
            False,
            "The model's holdout check couldn't run (not enough history), so predictions are hidden.",
            None,
        )
    if mape > CLV_MAPE_LIMIT:
        return (
            True,
            False,
            (
                f"Hidden: on a 180-day holdout the model missed actual revenue by {mape:.0%} "
                "(limit 30%). A bad prediction is worse than none."
            ),
            mape,
        )
    return True, True, None, mape
