from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from apps.api.auth import CurrentUser
from apps.api.cache import cached
from apps.api.db import DataVersion, db
from apps.api.filters import DimsDep, MonthRangeDep, strict
from apps.api.schemas import Envelope, FirstProduct, SecondOrder
from apps.api.services.findings import first_purchase_findings, timing_finding
from apps.api.services.repeat import first_product, second_order
from apps.api.services.version_info import meta_for

router = APIRouter(prefix="/v1/repeat", tags=["repeat"])
DIMS = ("from", "to", "channel", "country", "category")


def _filters(rng, dims, **extra) -> dict:
    return {
        "from": rng.start.isoformat() if rng.start else None,
        "to": rng.end.isoformat() if rng.end else None,
        **dims.as_dict(),
        **extra,
    }


@router.get(
    "/second-order",
    response_model=Envelope[SecondOrder],
    dependencies=[strict(*DIMS)],
    summary="Time-to-second-order histogram with median and 90th percentile",
)
async def second_order_route(
    request: Request, user: CurrentUser, rng: MonthRangeDep, dims: DimsDep
):
    async def compute(v: DataVersion) -> Envelope[SecondOrder]:
        async with db.ro.connect() as conn:
            so = await second_order(conn, rng, dims)
        t = timing_finding(so, dims)
        so.findings = [t] if t else []
        return Envelope[SecondOrder](
            data=so, meta=await meta_for(v, _filters(rng, dims), ["time_to_second_order"])
        )

    return await cached(request, compute)


@router.get(
    "/first-product",
    response_model=Envelope[FirstProduct],
    dependencies=[strict(*DIMS, "level", "min_buyers")],
    summary="First product or category → repeat within 90 days, sorted by effect size",
)
async def first_product_route(
    request: Request,
    user: CurrentUser,
    rng: MonthRangeDep,
    dims: DimsDep,
    level: Annotated[Literal["category", "product"], Query()] = "category",
    min_buyers: Annotated[int, Query(ge=30, le=10_000)] = 30,
):
    async def compute(v: DataVersion) -> Envelope[FirstProduct]:
        async with db.ro.connect() as conn:
            fp = await first_product(conn, level, rng, dims, min_buyers)
        fp.findings = first_purchase_findings(fp, dims)
        return Envelope[FirstProduct](
            data=fp,
            meta=await meta_for(v, _filters(rng, dims, level=level), ["repeat_90d"]),
        )

    return await cached(request, compute)
