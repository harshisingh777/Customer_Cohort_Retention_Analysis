"""Filter parsing and validation. Dimension values are checked against the allowed lists for
the current data version, dates are clamped to the data bounds, and unknown parameters are
rejected so a typo never silently returns unfiltered numbers."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Annotated, Literal

from fastapi import Depends, Query, Request
from sqlalchemy import Select, func, select

from apps.api.cache import require_version
from apps.api.db import db
from apps.api.errors import Problem
from apps.api.tables import customer_state, retention_monthly, retention_weekly

Granularity = Literal["month", "week"]
Measure = Literal["customers", "revenue", "cumulative"]


@dataclass
class Bounds:
    min_month: dt.date | None
    max_month: dt.date | None
    min_week: dt.date | None
    max_week: dt.date | None
    channels: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)


_bounds: dict[str, Bounds] = {}


async def load_bounds() -> Bounds:
    v = require_version()
    if v.version in _bounds:
        return _bounds[v.version]
    async with db.ro.connect() as conn:
        m = (
            await conn.execute(
                select(
                    func.min(retention_monthly.c.cohort_month),
                    func.max(retention_monthly.c.cohort_month),
                )
            )
        ).one()
        w = (
            await conn.execute(
                select(
                    func.min(retention_weekly.c.cohort_week),
                    func.max(retention_weekly.c.cohort_week),
                )
            )
        ).one()

        async def distinct(col) -> list[str]:
            rows = await conn.execute(
                select(col, func.count()).group_by(col).order_by(func.count().desc(), col)
            )
            return [r[0] for r in rows]

        b = Bounds(
            m[0],
            m[1],
            w[0],
            w[1],
            await distinct(customer_state.c.acquisition_channel),
            await distinct(customer_state.c.country),
            await distinct(customer_state.c.first_category),
        )
    _bounds.clear()
    _bounds[v.version] = b
    return b


def parse_period(value: str | None, name: str) -> dt.date | None:
    if not value:
        return None
    try:
        if len(value) == 7:
            return dt.date.fromisoformat(value + "-01")
        return dt.date.fromisoformat(value)
    except ValueError:
        raise Problem(
            422,
            "invalid-request",
            "Invalid request",
            f"Invalid value for {name}: use YYYY-MM or YYYY-MM-DD.",
        ) from None


@dataclass
class Dims:
    channel: list[str]
    country: list[str]
    category: list[str]

    def apply(self, stmt: Select, table) -> Select:
        if self.channel:
            stmt = stmt.where(table.c.acquisition_channel.in_(self.channel))
        if self.country:
            stmt = stmt.where(table.c.country.in_(self.country))
        if self.category:
            stmt = stmt.where(table.c.first_category.in_(self.category))
        return stmt

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "channel": self.channel or ["all"],
            "country": self.country or ["all"],
            "category": self.category or ["all"],
        }


@dataclass
class Range:
    start: dt.date | None
    end: dt.date | None

    def apply(self, stmt: Select, col) -> Select:
        if self.start:
            stmt = stmt.where(col >= self.start)
        if self.end:
            stmt = stmt.where(col <= self.end)
        return stmt


def strict(*allowed: str):
    """Dependency factory: reject query parameters a route doesn't accept."""
    names = set(allowed) | {"_"}

    async def check(request: Request) -> None:
        unknown = sorted(set(request.query_params.keys()) - names)
        if unknown:
            raise Problem(
                422,
                "unknown-parameter",
                "Unknown parameter",
                f"Unknown parameter{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}.",
            )

    return Depends(check)


async def dims(
    channel: Annotated[list[str] | None, Query(description="Acquisition channel(s)")] = None,
    country: Annotated[list[str] | None, Query(description="Country at first order")] = None,
    category: Annotated[list[str] | None, Query(description="Category of the first order")] = None,
) -> Dims:
    b = await load_bounds()
    for name, values, allowed in (
        ("channel", channel, b.channels),
        ("country", country, b.countries),
        ("category", category, b.categories),
    ):
        bad = [v for v in values or [] if v not in allowed]
        if bad:
            raise Problem(
                422,
                "invalid-filter",
                "Invalid filter",
                f"Unknown {name}: {', '.join(bad)}. Pick from the values in the filter menu.",
            )
    return Dims(channel or [], country or [], category or [])


def _clamp(d: dt.date | None, lo: dt.date | None, hi: dt.date | None) -> dt.date | None:
    if d is None:
        return None
    if lo and d < lo:
        return lo
    if hi and d > hi:
        return hi
    return d


async def cohort_range(
    granularity: Annotated[Granularity, Query()] = "month",
    from_: Annotated[
        str | None, Query(alias="from", description="First cohort, YYYY-MM or YYYY-MM-DD")
    ] = None,
    to: Annotated[str | None, Query(description="Last cohort, YYYY-MM or YYYY-MM-DD")] = None,
) -> Range:
    b = await load_bounds()
    start, end = parse_period(from_, "from"), parse_period(to, "to")
    if granularity == "month":
        start = start.replace(day=1) if start else None
        end = end.replace(day=1) if end else None
        lo, hi = b.min_month, b.max_month
    else:
        start = start - dt.timedelta(days=start.weekday()) if start else None
        end = end - dt.timedelta(days=end.weekday()) if end else None
        lo, hi = b.min_week, b.max_week
    start, end = _clamp(start, lo, hi), _clamp(end, lo, hi)
    if start and end and start > end:
        raise Problem(
            422, "invalid-range", "Invalid range", "The start of the range is after its end."
        )
    return Range(start, end)


async def month_range(
    from_: Annotated[
        str | None, Query(alias="from", description="First cohort month, YYYY-MM")
    ] = None,
    to: Annotated[str | None, Query(description="Last cohort month, YYYY-MM")] = None,
) -> Range:
    return await cohort_range("month", from_, to)


DimsDep = Annotated[Dims, Depends(dims)]
RangeDep = Annotated[Range, Depends(cohort_range)]
MonthRangeDep = Annotated[Range, Depends(month_range)]
