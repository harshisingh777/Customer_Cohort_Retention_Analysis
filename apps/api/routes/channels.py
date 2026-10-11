from __future__ import annotations

from fastapi import APIRouter, Request

from apps.api.auth import CurrentUser
from apps.api.cache import cached
from apps.api.db import DataVersion, db
from apps.api.filters import MonthRangeDep, strict
from apps.api.schemas import Channels, Envelope
from apps.api.services.channels import compute_channels
from apps.api.services.version_info import meta_for

router = APIRouter(prefix="/v1", tags=["channels"])


@router.get(
    "/channels",
    response_model=Envelope[Channels],
    dependencies=[strict("from", "to")],
    summary="Channel performance: CAC, LTV, LTV:CAC and payback (spend is per channel only)",
)
async def channels(request: Request, user: CurrentUser, rng: MonthRangeDep):
    async def compute(v: DataVersion) -> Envelope[Channels]:
        async with db.ro.connect() as conn:
            data = await compute_channels(conn, rng)
        filters = {
            "from": rng.start.isoformat() if rng.start else None,
            "to": rng.end.isoformat() if rng.end else None,
        }
        return Envelope[Channels](
            data=data,
            meta=await meta_for(
                v,
                filters,
                [
                    "cac",
                    "ltv_cac",
                    "payback_month",
                    "historical_ltv",
                    "predicted_ltv_12m",
                    "attribution_coverage",
                ],
            ),
        )

    return await cached(request, compute)
