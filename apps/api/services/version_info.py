"""Facts fixed per data version (the settings the marts were built with), cached per version."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from apps.api.cache import require_version
from apps.api.db import DataVersion, db
from apps.api.schemas import Meta
from apps.api.tables import data_quality


@dataclass
class VersionInfo:
    timezone: str
    currency: str
    lapse_threshold_days: int | None


_info: dict[str, VersionInfo] = {}


async def version_info() -> VersionInfo:
    v = require_version()
    if v.version not in _info:
        async with db.ro.connect() as conn:
            row = (
                await conn.execute(
                    select(
                        data_quality.c.reporting_tz,
                        data_quality.c.reporting_currency,
                        data_quality.c.lapse_threshold_days,
                    )
                )
            ).first()
        _info.clear()
        _info[v.version] = (
            VersionInfo(row.reporting_tz, row.reporting_currency, row.lapse_threshold_days)
            if row
            else VersionInfo("UTC", "GBP", None)
        )
    return _info[v.version]


async def meta_for(v: DataVersion, filters: dict, metrics: list[str]) -> Meta:
    info = await version_info()
    return Meta(
        data_version=v.version,
        data_through=v.data_through,
        timezone=info.timezone,
        currency=info.currency,
        filters=filters,
        metrics=metrics,
    )
