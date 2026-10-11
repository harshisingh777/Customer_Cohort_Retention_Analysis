"""Summary vitals: the latest comparable period against the one before, per metric. Each
metric picks its own latest *fully observed* period, so a 90-day rate is never computed on
customers who haven't had 90 days."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from apps.api import metrics_math as mm
from apps.api.filters import Dims
from apps.api.schemas import Vital, VitalPoint
from apps.api.tables import lapse_monthly, ltv_cohort


def _m(d: dt.date) -> str:
    return d.strftime("%b %Y")


def _pair(points: list[VitalPoint]) -> tuple[VitalPoint | None, VitalPoint | None]:
    cur = points[-1] if points else None
    prev = points[-2] if len(points) > 1 else None
    return cur, prev


async def vitals(conn: AsyncConnection, dims: Dims) -> list[Vital]:
    t = ltv_cohort
    stmt = (
        select(
            t.c.cohort_month,
            func.sum(t.c.customers).label("customers"),
            func.sum(t.c.repeat_eligible_90d).label("rep_elig"),
            func.sum(t.c.repeat_90d).label("rep"),
            func.sum(t.c.eligible_365d).label("ltv_elig"),
            func.sum(t.c.ltv_365d_sum).label("ltv_sum"),
        )
        .group_by(t.c.cohort_month)
        .order_by(t.c.cohort_month)
    )
    rows = (await conn.execute(dims.apply(stmt, t))).all()
    # The incomplete current month never appears: marts only hold complete cohorts' customers,
    # but int_customer_acquisition includes it, so drop months after the last lapse month end.
    lt = lapse_monthly
    lstmt = (
        select(
            lt.c.month_end,
            func.sum(lt.c.base_customers).label("base"),
            func.sum(lt.c.lapsed_customers).label("lapsed"),
        )
        .group_by(lt.c.month_end)
        .order_by(lt.c.month_end)
    )
    lapse_rows = (await conn.execute(dims.apply(lstmt, lt))).all()
    last_complete = lapse_rows[-1].month_end.replace(day=1) if lapse_rows else None
    rows = [r for r in rows if last_complete is None or r.cohort_month <= last_complete]

    new_pts = [
        VitalPoint(label=_m(r.cohort_month), value=float(r.customers), n=int(r.customers))
        for r in rows
    ]
    rep_pts = [
        VitalPoint(
            label=f"{_m(r.cohort_month)} cohort",
            value=mm.rate(int(r.rep), int(r.rep_elig)),
            n=int(r.rep_elig),
        )
        for r in rows
        if r.customers and r.rep_elig == r.customers
    ]
    ltv_pts = [
        VitalPoint(
            label=f"{_m(r.cohort_month)} cohort",
            value=float(r.ltv_sum) / int(r.ltv_elig),
            n=int(r.ltv_elig),
        )
        for r in rows
        if r.customers and r.ltv_elig == r.customers
    ]
    lapse_pts = [
        VitalPoint(label=_m(r.month_end), value=mm.rate(int(r.lapsed), int(r.base)), n=int(r.base))
        for r in lapse_rows
        if r.base
    ]

    out = []
    for vid, metric, label, kind, pts in (
        ("new_customers", "new_customers", "New customers", "count", new_pts),
        ("repeat_90d", "repeat_90d", "Repeat within 90 days", "rate", rep_pts),
        ("lapse_rate", "lapse_rate", "Lapse rate", "rate", lapse_pts),
        ("ltv_365", "historical_ltv", "365-day LTV", "currency", ltv_pts),
    ):
        cur, prev = _pair(pts)
        out.append(
            Vital(
                id=vid,
                metric_id=metric,
                label=label,
                kind=kind,  # type: ignore[arg-type]
                current=cur,
                previous=prev,
                change=mm.change(cur.value if cur else None, prev.value if prev else None, kind),
            )
        )
    return out
