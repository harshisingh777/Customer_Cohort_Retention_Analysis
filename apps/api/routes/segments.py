from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from sqlalchemy import func, select

from apps.api.auth import CurrentUser
from apps.api.cache import cached
from apps.api.db import DataVersion, db
from apps.api.errors import Problem
from apps.api.filters import DimsDep, MonthRangeDep, strict
from apps.api.schemas import CustomerDetail, CustomerPage, Envelope, Rfm, RfmCell, RfmSegment
from apps.api.services.customers import Sort, State, customer_detail, customer_page
from apps.api.services.store import clv_status
from apps.api.services.version_info import meta_for
from apps.api.tables import rfm_cells

router = APIRouter(prefix="/v1", tags=["segments", "customers"])
DIMS = ("from", "to", "channel", "country", "category")
SEGMENTS = [
    "Champions",
    "Loyal",
    "Potential loyalists",
    "New customers",
    "Needs attention",
    "Can't lose them",
    "At risk",
    "Lost",
]


def _filters(rng, dims, **extra) -> dict:
    return {
        "from": rng.start.isoformat() if rng.start else None,
        "to": rng.end.isoformat() if rng.end else None,
        **dims.as_dict(),
        **extra,
    }


@router.get(
    "/segments/rfm",
    response_model=Envelope[Rfm],
    dependencies=[strict(*DIMS)],
    summary="5x5 Recency x Frequency grid with segment totals",
)
async def rfm(request: Request, user: CurrentUser, rng: MonthRangeDep, dims: DimsDep):
    async def compute(v: DataVersion) -> Envelope[Rfm]:
        t = rfm_cells
        stmt = select(
            t.c.rfm_r,
            t.c.rfm_f,
            t.c.rfm_segment,
            func.sum(t.c.customers).label("n"),
            func.sum(t.c.net_revenue).label("rev"),
            func.sum(t.c.lapsed_customers).label("lapsed"),
        ).group_by(t.c.rfm_r, t.c.rfm_f, t.c.rfm_segment)
        async with db.ro.connect() as conn:
            rows = (await conn.execute(rng.apply(dims.apply(stmt, t), t.c.cohort_month))).all()
        total = sum(int(r.n) for r in rows)
        cells = [
            RfmCell(
                r=r.rfm_r,
                f=r.rfm_f,
                segment=r.rfm_segment,
                customers=int(r.n),
                avg_value=float(r.rev) / int(r.n) if r.n else None,
                lapsed=int(r.lapsed),
            )
            for r in rows
        ]
        segs: dict[str, list[float]] = {}
        for r in rows:
            acc = segs.setdefault(r.rfm_segment, [0, 0.0])
            acc[0] += int(r.n)
            acc[1] += float(r.rev)
        segments = [
            RfmSegment(
                name=name,
                customers=int(n),
                share=n / total if total else 0.0,
                net_revenue=rev,
                avg_value=rev / n if n else None,
            )
            for name in SEGMENTS
            if name in segs
            for n, rev in [segs[name]]
        ]
        return Envelope[Rfm](
            data=Rfm(cells=cells, segments=segments, total_customers=total),
            meta=await meta_for(v, _filters(rng, dims), ["rfm_segment"]),
        )

    return await cached(request, compute)


async def _list(request: Request, user, rng, dims, segment, state, sort, cursor, limit):
    if segment is not None and segment not in SEGMENTS:
        raise Problem(404, "not-found", "Not found", f"There is no segment called {segment!r}.")

    async def compute(v: DataVersion) -> Envelope[CustomerPage]:
        async with db.ro.connect() as conn:
            _, visible, _, _ = await clv_status(conn)
            page = await customer_page(
                conn,
                rng=rng,
                dims=dims,
                segment=segment,
                state=state,
                sort=sort,
                cursor=cursor,
                limit=limit,
                reveal=user.is_admin,
                clv_visible=visible,
            )
        return Envelope[CustomerPage](
            data=page,
            meta=await meta_for(
                v,
                _filters(rng, dims, segment=segment, state=state, sort=sort),
                ["rfm_segment", "lapse_rate", "p_alive", "predicted_ltv_12m"],
            ),
        )

    # Viewers and admins see different emails, so the role is part of the cache key.
    return await cached(request, compute, vary=(user.role,))


LIST_PARAMS = (*DIMS, "segment", "state", "sort", "cursor", "limit")


@router.get(
    "/customers",
    response_model=Envelope[CustomerPage],
    dependencies=[strict(*LIST_PARAMS)],
    summary="Customers, keyset-paginated. Emails are masked for viewers.",
)
async def customers(
    request: Request,
    user: CurrentUser,
    rng: MonthRangeDep,
    dims: DimsDep,
    segment: Annotated[str | None, Query()] = None,
    state: Annotated[State, Query()] = "all",
    sort: Annotated[Sort, Query()] = "value",
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    return await _list(request, user, rng, dims, segment, state, sort, cursor, limit)


@router.get(
    "/segments/{segment}/customers",
    response_model=Envelope[CustomerPage],
    dependencies=[strict(*DIMS, "state", "sort", "cursor", "limit")],
    summary="Customers in one RFM segment",
)
async def segment_customers(
    request: Request,
    user: CurrentUser,
    rng: MonthRangeDep,
    dims: DimsDep,
    segment: Annotated[str, Path()],
    state: Annotated[State, Query()] = "all",
    sort: Annotated[Sort, Query()] = "value",
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    return await _list(request, user, rng, dims, segment, state, sort, cursor, limit)


@router.get(
    "/customers/{customer_key}",
    response_model=Envelope[CustomerDetail],
    dependencies=[strict()],
    summary="One customer with their order timeline. Email masked for viewers.",
)
async def customer(
    request: Request, user: CurrentUser, customer_key: Annotated[str, Path(max_length=200)]
):
    async def compute(v: DataVersion) -> Envelope[CustomerDetail]:
        async with db.ro.connect() as conn:
            _, visible, _, _ = await clv_status(conn)
            detail = await customer_detail(conn, customer_key, user.is_admin, visible)
        return Envelope[CustomerDetail](
            data=detail, meta=await meta_for(v, {}, ["p_alive", "predicted_ltv_12m"])
        )

    return await cached(request, compute, vary=(user.role,))
