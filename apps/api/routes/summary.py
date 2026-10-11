from __future__ import annotations

from fastapi import APIRouter, Request

from apps.api.auth import CurrentUser
from apps.api.cache import cached
from apps.api.db import DataVersion, db
from apps.api.filters import DimsDep, MonthRangeDep, strict
from apps.api.schemas import Envelope, Summary
from apps.api.services.cohorts import cohort_rows
from apps.api.services.findings import (
    cohort_findings,
    first_purchase_findings,
    pick,
    timing_finding,
)
from apps.api.services.repeat import first_product, second_order
from apps.api.services.version_info import meta_for
from apps.api.services.vitals import vitals

router = APIRouter(prefix="/v1", tags=["summary"])
LOW_REPEAT = 0.10


@router.get(
    "/summary",
    response_model=Envelope[Summary],
    dependencies=[strict("from", "to", "channel", "country", "category")],
    summary="Findings and vitals for the Summary page",
)
async def summary(request: Request, user: CurrentUser, rng: MonthRangeDep, dims: DimsDep):
    async def compute(v: DataVersion) -> Envelope[Summary]:
        async with db.ro.connect() as conn:
            cum = await cohort_rows(conn, "month", "cumulative", rng, dims)
            so = await second_order(conn, rng, dims)
            fp = await first_product(conn, "category", rng, dims, min_buyers=30)
            vit = await vitals(conn, dims)
        # Repeat is "rare" when under 10% of customers have a second order by month 3.
        old = [r for r in cum if len(r.active) > 3]
        size = sum(r.size for r in old)
        low_repeat = bool(size) and sum(r.active[3] for r in old) / size < LOW_REPEAT
        found = cohort_findings(cum, "month", dims) + first_purchase_findings(fp, dims)
        t = timing_finding(so, dims)
        if t:
            found.append(t)
        filters = {
            "from": rng.start.isoformat() if rng.start else None,
            "to": rng.end.isoformat() if rng.end else None,
            **dims.as_dict(),
        }
        return Envelope[Summary](
            data=Summary(
                findings=pick(found, low_repeat=low_repeat), vitals=vit, low_repeat=low_repeat
            ),
            meta=await meta_for(
                v, filters, ["new_customers", "repeat_90d", "lapse_rate", "historical_ltv"]
            ),
        )

    return await cached(request, compute)
