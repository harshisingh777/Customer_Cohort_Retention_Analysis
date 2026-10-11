"""Customer lists (keyset-paginated) and detail. Emails come only through
ops.customer_contacts(), which masks them unless the caller is an admin."""

from __future__ import annotations

import base64
import json
from typing import Literal

from sqlalchemy import Select, and_, bindparam, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.types import Boolean, Text

from apps.api.errors import Problem
from apps.api.filters import Dims, Range
from apps.api.schemas import CustomerDetail, CustomerOrder, CustomerPage, CustomerRow
from apps.api.tables import customer_clv, customer_state, int_orders

Sort = Literal["value", "recent", "orders", "risk"]
State = Literal["all", "active", "lapsed", "drifting"]
s, c = customer_state, customer_clv

SORTS = {
    # (sort expression, descending?)
    "value": (s.c.net_revenue, True),
    "recent": (s.c.last_order_date, True),
    "orders": (s.c.orders, True),
    "risk": (func.coalesce(c.c.p_alive, 1.0), False),
}


def _encode(values: list) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, default=str).encode()).decode()


def _decode(cursor: str) -> list:
    try:
        v = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(v, list) or len(v) != 2:
            raise ValueError
        return v
    except Exception:
        raise Problem(
            422,
            "invalid-cursor",
            "Invalid cursor",
            "This page link is out of date. Go back to the first page.",
        ) from None


def _base(rng: Range, dims: Dims, segment: str | None, state: State, clv_visible: bool) -> Select:
    cols = [
        s.c[k]
        for k in (
            "customer_key",
            "cohort_month",
            "acquisition_channel",
            "country",
            "first_category",
            "orders",
            "net_revenue",
            "last_order_date",
            "days_since_last",
            "is_lapsed",
            "rfm_segment",
            "rfm_r",
            "rfm_f",
            "rfm_m",
            "first_order_date",
            "avg_order_value",
            "ltv_90d",
            "ltv_180d",
            "ltv_365d",
            "first_product_name",
        )
    ]
    cols += [c.c.p_alive, c.c.pred_ltv_12m_p10, c.c.pred_ltv_12m_p50, c.c.pred_ltv_12m_p90]
    stmt = select(*cols).select_from(s.outerjoin(c, c.c.customer_key == s.c.customer_key))
    stmt = rng.apply(dims.apply(stmt, s), s.c.cohort_month)
    if segment:
        stmt = stmt.where(s.c.rfm_segment == segment)
    if state == "lapsed":
        stmt = stmt.where(s.c.is_lapsed)
    elif state == "active":
        stmt = stmt.where(~s.c.is_lapsed)
    elif state == "drifting":
        stmt = stmt.where(~s.c.is_lapsed, c.c.p_alive < 0.5)
    return stmt


async def _emails(conn: AsyncConnection, keys: list[str], reveal: bool) -> dict[str, str | None]:
    if not keys:
        return {}
    fn = func.ops.customer_contacts(
        bindparam("keys", keys, type_=ARRAY(Text)), bindparam("reveal", reveal, type_=Boolean)
    ).table_valued("customer_key", "email")
    rows = await conn.execute(select(fn.c.customer_key, fn.c.email))
    return {r.customer_key: r.email for r in rows}


def _row(r, email: str | None, clv_visible: bool) -> dict:
    p_alive = float(r.p_alive) if r.p_alive is not None else None
    return {
        "customer_key": r.customer_key,
        "email": email,
        "cohort": r.cohort_month.strftime("%Y-%m"),
        "channel": r.acquisition_channel,
        "country": r.country,
        "first_category": r.first_category,
        "orders": int(r.orders),
        "net_revenue": float(r.net_revenue),
        "last_order_date": r.last_order_date,
        "days_since_last": int(r.days_since_last),
        "is_lapsed": bool(r.is_lapsed),
        "is_drifting": (p_alive < 0.5 and not r.is_lapsed) if p_alive is not None else None,
        "segment": r.rfm_segment,
        "r": r.rfm_r,
        "f": r.rfm_f,
        "m": r.rfm_m,
        "p_alive": p_alive,
        "pred_ltv_p10": float(r.pred_ltv_12m_p10)
        if clv_visible and r.pred_ltv_12m_p10 is not None
        else None,
        "pred_ltv_p50": float(r.pred_ltv_12m_p50)
        if clv_visible and r.pred_ltv_12m_p50 is not None
        else None,
        "pred_ltv_p90": float(r.pred_ltv_12m_p90)
        if clv_visible and r.pred_ltv_12m_p90 is not None
        else None,
    }


async def customer_page(
    conn: AsyncConnection,
    *,
    rng: Range,
    dims: Dims,
    segment: str | None,
    state: State,
    sort: Sort,
    cursor: str | None,
    limit: int,
    reveal: bool,
    clv_visible: bool,
    with_total: bool = True,
) -> CustomerPage:
    expr, desc = SORTS[sort]
    stmt = _base(rng, dims, segment, state, clv_visible)
    total = 0
    if with_total:
        total = int(
            (await conn.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        )
    if cursor:
        last_value, last_key = _decode(cursor)
        key = tuple_(expr, s.c.customer_key)
        stmt = stmt.where(
            key < tuple_(bindparam("cv", last_value), bindparam("ck", last_key))
            if desc
            else key > tuple_(bindparam("cv", last_value), bindparam("ck", last_key))
        )
    order = [expr.desc(), s.c.customer_key.desc()] if desc else [expr.asc(), s.c.customer_key.asc()]
    stmt = stmt.add_columns(expr.label("_sort")).order_by(*order).limit(limit + 1)
    rows = (await conn.execute(stmt)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    emails = await _emails(conn, [r.customer_key for r in rows], reveal)
    next_cursor = None
    if more and rows:
        last = rows[-1]
        sort_value = last._sort
        next_cursor = _encode(
            [
                float(sort_value) if sort_value is not None and sort != "recent" else sort_value,
                last.customer_key,
            ]
        )
    return CustomerPage(
        rows=[CustomerRow(**_row(r, emails.get(r.customer_key), clv_visible)) for r in rows],
        next_cursor=next_cursor,
        total=total,
    )


async def customer_detail(
    conn: AsyncConnection, key: str, reveal: bool, clv_visible: bool
) -> CustomerDetail:
    stmt = _base(Range(None, None), Dims([], [], []), None, "all", clv_visible).where(
        s.c.customer_key == key
    )
    r = (await conn.execute(stmt)).first()
    if r is None:
        raise Problem(404, "not-found", "Not found", "This customer isn't in the current data.")
    emails = await _emails(conn, [key], reveal)
    orders = (
        await conn.execute(
            select(
                int_orders.c.order_id,
                int_orders.c.order_date_local,
                int_orders.c.net_revenue,
                int_orders.c.primary_category,
                int_orders.c.primary_product_name,
            )
            .where(int_orders.c.customer_key == key)
            .order_by(int_orders.c.order_seq)
        )
    ).all()
    base = _row(r, emails.get(key), clv_visible)
    return CustomerDetail(
        **base,
        first_order_date=r.first_order_date,
        avg_order_value=float(r.avg_order_value),
        ltv_90d=float(r.ltv_90d) if r.ltv_90d is not None else None,
        ltv_180d=float(r.ltv_180d) if r.ltv_180d is not None else None,
        ltv_365d=float(r.ltv_365d) if r.ltv_365d is not None else None,
        first_product=r.first_product_name,
        orders_timeline=[
            CustomerOrder(
                order_id=o.order_id,
                date=o.order_date_local,
                net_revenue=float(o.net_revenue),
                category=o.primary_category,
                product=o.primary_product_name,
            )
            for o in orders
        ],
    )


__all__ = ["and_", "customer_detail", "customer_page", "or_"]
