"""/meta, /metrics and /settings."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from apps.api.auth import AdminUser, CurrentUser
from apps.api.cache import uncached
from apps.api.db import db
from apps.api.errors import Problem
from apps.api.filters import load_bounds, strict
from apps.api.schemas import (
    DateBounds,
    Dimensions,
    MetaData,
    MetricDef,
    MetricsDoc,
    SettingsOut,
    SettingsSaved,
    SettingsUpdate,
)
from apps.api.services.store import clv_status, freshness, read_settings
from apps.api.tables import audit_t, channel_spend, data_quality, jobs_t, settings_t
from core.metrics_catalog import load_catalog
from core.store_settings import StoreSettings

router = APIRouter(prefix="/v1", tags=["meta"])


def _settings_out(s: StoreSettings) -> SettingsOut:
    return SettingsOut(**s.model_dump())


@router.get(
    "/meta",
    response_model=MetaData,
    dependencies=[strict()],
    summary="Data version, freshness, settings and allowed filter values",
)
async def meta(request: Request, user: CurrentUser):
    async with db.ro.connect() as conn:
        s = await read_settings(conn)
        fresh = await freshness(conn)
        v = db.current
        dims = Dimensions(channels=[], countries=[], categories=[])
        bounds = DateBounds(min_month=None, max_month=None, min_week=None, max_week=None)
        threshold = None
        has_spend = has_clv = clv_visible = False
        if v is not None:
            b = await load_bounds()
            dims = Dimensions(channels=b.channels, countries=b.countries, categories=b.categories)
            bounds = DateBounds(
                min_month=b.min_month,
                max_month=b.max_month,
                min_week=b.min_week,
                max_week=b.max_week,
            )
            threshold = (await conn.execute(select(data_quality.c.lapse_threshold_days))).scalar()
            has_spend = bool(
                (await conn.execute(select(func.count()).select_from(channel_spend))).scalar()
            )
            has_clv, clv_visible, _, _ = await clv_status(conn)
    payload = MetaData(
        data_version=v.version if v else None,
        data_through=v.data_through if v else None,
        published_at=v.published_at if v else None,
        store_name=s.store_name,
        timezone=s.reporting_tz,
        currency=s.reporting_currency,
        locale=s.locale,
        freshness=fresh,
        dimensions=dims,
        bounds=bounds,
        lapse_threshold_days=threshold,
        has_spend=has_spend,
        has_clv=has_clv,
        clv_visible=clv_visible,
        gross_margin=s.gross_margin,
        role=user.role,
        email=user.email,
    )
    return await uncached(request, payload, v)


@router.get(
    "/metrics",
    response_model=MetricsDoc,
    dependencies=[strict()],
    summary="Metric definitions (metrics.yml) and the current settings",
)
async def metrics(request: Request, user: CurrentUser):
    cat = load_catalog()
    async with db.ro.connect() as conn:
        s = await read_settings(conn)
        lapse = None
        if db.current is not None:
            row = (
                await conn.execute(
                    select(
                        data_quality.c.lapse_threshold_days,
                        data_quality.c.derived_threshold_days,
                        data_quality.c.override_threshold_days,
                        data_quality.c.p90_gap_days,
                        data_quality.c.gap_count,
                    )
                )
            ).first()
            lapse = (
                {
                    k: (float(v) if v is not None and k == "p90_gap_days" else v)
                    for k, v in row._mapping.items()
                }
                if row
                else None
            )
    payload = MetricsDoc(
        rules=cat.rules,
        metrics=[MetricDef(**m.model_dump()) for m in cat.metrics],
        settings=_settings_out(s),
        lapse_threshold=lapse,
    )
    return await uncached(request, payload, db.current)


@router.get(
    "/settings",
    response_model=SettingsOut,
    dependencies=[strict()],
    summary="Current settings (admin)",
)
async def get_settings(request: Request, user: AdminUser):
    async with db.ro.connect() as conn:
        return await uncached(request, _settings_out(await read_settings(conn)), db.current)


@router.put(
    "/settings", response_model=SettingsSaved, summary="Change settings; triggers a rebuild (admin)"
)
async def put_settings(body: SettingsUpdate, user: AdminUser) -> SettingsSaved:
    async with db.ro.connect() as conn:
        current = await read_settings(conn)
    changes = body.model_dump(exclude_unset=True, exclude={"clear"})
    changes = {k: v for k, v in changes.items() if v is not None}
    merged = current.model_dump()
    merged.update(changes)
    for key in body.clear:
        merged[key] = None
    try:
        new = StoreSettings.model_validate(merged)
    except ValidationError as e:
        first = e.errors()[0]
        raise Problem(
            422,
            "invalid-settings",
            "Invalid settings",
            f"{'.'.join(str(x) for x in first['loc'])}: {first['msg']}.",
        ) from None
    diff = {
        k: v
        for k, v in new.model_dump(mode="json").items()
        if v != current.model_dump(mode="json").get(k)
    }
    if not diff:
        return SettingsSaved(settings=_settings_out(new), rebuild_job_id=None)

    async with db.ops.begin() as conn:
        for key, value in diff.items():
            stmt = pg_insert(settings_t).values(key=key, value=value, updated_by=user.email)
            await conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[settings_t.c.key],
                    set_={
                        "value": stmt.excluded.value,
                        "updated_at": func.now(),
                        "updated_by": user.email,
                    },
                )
            )
        await conn.execute(
            insert(audit_t).values(
                actor=user.email,
                action="settings.update",
                detail=json.loads(json.dumps(diff, default=str)),
            )
        )
        # Store name and refresh time don't change any metric; everything else needs a rebuild.
        job_id = None
        if set(diff) - {"store_name", "refresh_time_local", "clv_weekday"}:
            job_id = (
                await conn.execute(
                    insert(jobs_t)
                    .values(kind="refresh", payload={"trigger": "settings"}, created_by=user.email)
                    .returning(jobs_t.c.id)
                )
            ).scalar_one()
    return SettingsSaved(settings=_settings_out(new), rebuild_job_id=job_id)
