"""Cohort tables and curves: SUM over the additive marts, then rates and intervals."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from apps.api import metrics_math as mm
from apps.api.filters import Dims, Granularity, Measure, Range
from apps.api.schemas import CohortRow, Curves, CurveSeries
from apps.api.tables import retention_monthly, retention_weekly


def cohort_label(d: dt.date, granularity: str) -> str:
    return d.strftime("%Y-%m") if granularity == "month" else d.isoformat()


def human_cohort(d: dt.date, granularity: str) -> str:
    return d.strftime("%B %Y") if granularity == "month" else f"the week of {d.day} {d:%b %Y}"


async def cohort_rows(
    conn: AsyncConnection, granularity: Granularity, measure: Measure, rng: Range, dims: Dims
) -> list[CohortRow]:
    t = retention_monthly if granularity == "month" else retention_weekly
    cohort_col = t.c.cohort_month if granularity == "month" else t.c.cohort_week
    stmt = (
        select(
            cohort_col.label("cohort"),
            t.c.period_number,
            func.sum(t.c.cohort_customers).label("size"),
            func.sum(t.c.active_customers).label("active"),
            func.sum(t.c.cum_repeat_customers).label("cum"),
            func.sum(t.c.net_revenue).label("revenue"),
        )
        .group_by(cohort_col, t.c.period_number)
        .order_by(cohort_col, t.c.period_number)
    )
    stmt = rng.apply(dims.apply(stmt, t), cohort_col)
    rows = (await conn.execute(stmt)).all()

    grouped: dict[dt.date, list] = {}
    for r in rows:
        grouped.setdefault(r.cohort, []).append(r)

    out: list[CohortRow] = []
    for cohort, cells in grouped.items():
        cells.sort(key=lambda r: r.period_number)
        size = int(cells[0].size)
        rate: list[float | None] = []
        low: list[float | None] = []
        high: list[float | None] = []
        if measure == "revenue":
            values = [float(c.revenue) for c in cells]
            base = values[0]
            rate = [v / base if base else None for v in values]
            low = [None] * len(values)
            high = [None] * len(values)
        else:
            counts = [int(c.active if measure == "customers" else c.cum) for c in cells]
            values = [float(v) for v in counts]
            for k in counts:
                rate.append(mm.rate(k, size))
                ci = mm.wilson(k, size)
                low.append(round(ci[0], 4) if ci else None)
                high.append(round(ci[1], 4) if ci else None)
        out.append(
            CohortRow(
                cohort=cohort_label(cohort, granularity),
                size=size,
                active=values,
                rate=[round(x, 4) if x is not None else None for x in rate],
                low=low,
                high=high,
            )
        )
    return out


def curves_from_rows(rows: list[CohortRow], granularity: Granularity, measure: Measure) -> Curves:
    periods = list(range(max((len(r.rate) for r in rows), default=0)))
    last_six = rows[-6:]
    median: list[float | None] = []
    for p in periods:
        vals = [r.rate[p] for r in last_six if p < len(r.rate) and r.rate[p] is not None]
        median.append(round(mm.median(vals), 4) if len(vals) >= 3 else None)  # type: ignore[arg-type]
    return Curves(
        granularity=granularity,
        measure=measure,
        periods=periods,  # type: ignore[arg-type]
        series=[CurveSeries(cohort=r.cohort, size=r.size, values=r.rate) for r in rows],
        median=median,
        median_of=[r.cohort for r in last_six],
    )
