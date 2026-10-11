from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from apps.api.auth import CurrentUser
from apps.api.cache import cached
from apps.api.db import DataVersion, db
from apps.api.filters import DimsDep, Granularity, Measure, RangeDep, strict
from apps.api.schemas import CohortTable, Curves, Envelope
from apps.api.services.cohorts import cohort_rows, curves_from_rows
from apps.api.services.findings import cohort_findings, pick
from apps.api.services.version_info import meta_for

router = APIRouter(prefix="/v1/cohorts", tags=["cohorts"])
PARAMS = ("granularity", "measure", "from", "to", "channel", "country", "category")
METRIC_FOR = {
    "customers": "retention_rate",
    "revenue": "revenue_retention",
    "cumulative": "cumulative_repeat",
}


def _filters(granularity: str, measure: str, rng, dims) -> dict:
    return {
        "granularity": granularity,
        "measure": measure,
        "from": rng.start.isoformat() if rng.start else None,
        "to": rng.end.isoformat() if rng.end else None,
        **dims.as_dict(),
    }


@router.get(
    "/retention",
    response_model=Envelope[CohortTable],
    dependencies=[strict(*PARAMS)],
    summary="Cohort table. Arrays end where observability ends; the client never invents zeros.",
)
async def retention(
    request: Request,
    user: CurrentUser,
    rng: RangeDep,
    dims: DimsDep,
    granularity: Annotated[Granularity, Query()] = "month",
    measure: Annotated[Measure, Query()] = "customers",
):
    async def compute(v: DataVersion) -> Envelope[CohortTable]:
        async with db.ro.connect() as conn:
            rows = await cohort_rows(conn, granularity, measure, rng, dims)
            cum = (
                rows
                if measure == "cumulative"
                else await cohort_rows(conn, granularity, "cumulative", rng, dims)
            )
        table = CohortTable(
            granularity=granularity,
            measure=measure,
            periods=list(range(max((len(r.rate) for r in rows), default=0))),
            cohorts=rows,
            findings=pick(cohort_findings(cum, granularity, dims)),
        )
        return Envelope[CohortTable](
            data=table,
            meta=await meta_for(
                v, _filters(granularity, measure, rng, dims), [METRIC_FOR[measure], "cohort_size"]
            ),
        )

    return await cached(request, compute)


@router.get(
    "/curves",
    response_model=Envelope[Curves],
    dependencies=[strict(*PARAMS)],
    summary="One series per cohort plus the median of the last six cohorts",
)
async def curves(
    request: Request,
    user: CurrentUser,
    rng: RangeDep,
    dims: DimsDep,
    granularity: Annotated[Granularity, Query()] = "month",
    measure: Annotated[Measure, Query()] = "cumulative",
):
    async def compute(v: DataVersion) -> Envelope[Curves]:
        async with db.ro.connect() as conn:
            rows = await cohort_rows(conn, granularity, measure, rng, dims)
        return Envelope[Curves](
            data=curves_from_rows(rows, granularity, measure),
            meta=await meta_for(
                v, _filters(granularity, measure, rng, dims), [METRIC_FOR[measure]]
            ),
        )

    return await cached(request, compute)
