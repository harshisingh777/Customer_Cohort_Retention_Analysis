"""Time to second order and first purchase → repeat, from additive marts."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from apps.api import metrics_math as mm
from apps.api.filters import Dims, Range
from apps.api.schemas import FirstProduct, FirstProductRow, HistBin, SecondOrder, StoreRate
from apps.api.tables import customer_state, first_product_repeat, second_order_days

BIN_DAYS = 7
OPEN_BIN_START = 182


async def second_order(conn: AsyncConnection, rng: Range, dims: Dims) -> SecondOrder:
    t = second_order_days
    stmt = select(t.c.days_to_second, func.sum(t.c.customers).label("n")).group_by(
        t.c.days_to_second
    )
    stmt = rng.apply(dims.apply(stmt, t), t.c.cohort_month)
    hist = [(int(r.days_to_second), int(r.n)) for r in await conn.execute(stmt)]

    fb = select(func.count()).select_from(customer_state)
    first_buyers = int(
        (
            await conn.execute(
                rng.apply(dims.apply(fb, customer_state), customer_state.c.cohort_month)
            )
        ).scalar_one()
    )

    bins: list[HistBin] = []
    for start in range(0, OPEN_BIN_START, BIN_DAYS):
        bins.append(
            HistBin(
                start=start,
                end=start + BIN_DAYS - 1,
                customers=sum(c for d, c in hist if start <= d < start + BIN_DAYS),
            )
        )
    bins.append(
        HistBin(
            start=OPEN_BIN_START, end=None, customers=sum(c for d, c in hist if d >= OPEN_BIN_START)
        )
    )
    repeaters = sum(c for _, c in hist)
    after_90 = sum(c for d, c in hist if d >= 90)
    return SecondOrder(
        bins=bins,
        median_days=mm.hist_percentile(hist, 0.5),
        p90_days=mm.hist_percentile(hist, 0.9),
        repeaters=repeaters,
        first_buyers=first_buyers,
        share_after_90=round(after_90 / repeaters, 4) if repeaters else None,
    )


async def first_product(
    conn: AsyncConnection,
    level: Literal["category", "product"],
    rng: Range,
    dims: Dims,
    min_buyers: int,
) -> FirstProduct:
    t = first_product_repeat
    stmt = (
        select(
            t.c.item_id,
            func.max(t.c.item_label).label("label"),
            func.sum(t.c.first_buyers).label("first_buyers"),
            func.sum(t.c.eligible_90d).label("eligible"),
            func.sum(t.c.repeat_90d).label("repeaters"),
        )
        .where(t.c.level == level)
        .group_by(t.c.item_id)
    )
    stmt = rng.apply(dims.apply(stmt, t), t.c.cohort_month)
    items = (await conn.execute(stmt)).all()

    store_eligible = sum(int(r.eligible) for r in items)
    store_repeaters = sum(int(r.repeaters) for r in items)
    store_rate = mm.rate(store_repeaters, store_eligible)

    rows: list[FirstProductRow] = []
    hidden = 0
    for r in items:
        eligible, repeaters = int(r.eligible), int(r.repeaters)
        if eligible < min_buyers:
            hidden += 1
            continue
        rate = mm.rate(repeaters, eligible)
        ci = mm.wilson(repeaters, eligible)
        rows.append(
            FirstProductRow(
                item_id=r.item_id,
                label=r.label,
                first_buyers=int(r.first_buyers),
                eligible=eligible,
                repeaters=repeaters,
                rate=round(rate, 4) if rate is not None else None,
                low=round(ci[0], 4) if ci else None,
                high=round(ci[1], 4) if ci else None,
                diff_pts=round((rate - store_rate) * 100, 1)
                if rate is not None and store_rate is not None
                else None,
            )
        )
    rows.sort(key=lambda x: (-abs(x.diff_pts or 0), -x.eligible))
    return FirstProduct(
        level=level,
        min_buyers=min_buyers,  # type: ignore[arg-type]
        store=StoreRate(
            eligible=store_eligible,
            repeaters=store_repeaters,
            rate=round(store_rate, 4) if store_rate is not None else None,
        ),
        rows=rows,
        hidden_small=hidden,
    )
