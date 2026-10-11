"""Daily reference FX rates (ECB, via the Frankfurter API) for every order currency that
differs from the reporting currency. Staging converts at the latest rate on or before the
order date, so weekends and holidays use the previous business day."""

from __future__ import annotations

import datetime as dt
import logging

import httpx

from core.db import Conn
from pipeline.ingest.core import upsert_fx

log = logging.getLogger(__name__)
FEED = "https://api.frankfurter.app"

_CURRENCIES_SQL = """
select upper(coalesce(payload->>'currency', payload->>'currencyCode')) as ccy,
       min(source_updated_at)::date as first_day
from raw.orders
where coalesce(payload->>'currency', payload->>'currencyCode') is not null
group by 1
"""


def refresh_fx(conn: Conn, reporting_currency: str, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    fetched: dict[str, int] = {}
    for row in conn.execute(_CURRENCIES_SQL).fetchall():
        ccy, first_day = row["ccy"], row["first_day"]  # type: ignore[index]
        if ccy == reporting_currency.upper():
            continue
        have = conn.execute(
            "select max(date) as d from raw.fx_rates where base = %s and quote = %s",
            (ccy, reporting_currency),
        ).fetchone()
        start = (
            (have["d"] + dt.timedelta(days=1))
            if have and have["d"]
            else first_day - dt.timedelta(days=10)
        )  # type: ignore[index]
        if start > today:
            continue
        try:
            r = httpx.get(
                f"{FEED}/{start.isoformat()}..{today.isoformat()}",
                params={"from": ccy, "to": reporting_currency},
                timeout=30,
                follow_redirects=True,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            # Missing FX fails the reconciliation audit loudly rather than silently mis-converting.
            log.warning("fx fetch failed", extra={"currency": ccy, "error": str(e)})
            continue
        rows = [
            (dt.date.fromisoformat(d), ccy, reporting_currency, float(v[reporting_currency]))
            for d, v in r.json().get("rates", {}).items()
            if reporting_currency in v
        ]
        upsert_fx(conn, rows)
        fetched[ccy] = len(rows)
    return fetched
