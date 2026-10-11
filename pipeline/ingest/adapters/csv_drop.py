"""Generic CSV drop, for platforms without an adapter (spec §7.4).

Expected files in one folder (any subset; orders is required):

  orders.csv       order_id, created_at (ISO 8601 with offset), status, currency,
                   customer_id, email, country, test, utm_source, utm_medium, referrer,
                   discount_codes (semicolon separated), updated_at (optional)
  order_items.csv  line_id, order_id, sku, product_name, category, quantity, unit_price,
                   currency, line_type (product | shipping | fee | adjustment)
  refunds.csv      refund_id, order_id, amount, currency, created_at
  customers.csv    customer_id, email, country, created_at
  spend.csv        date, channel, spend_amount, currency
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from pipeline.ingest.core import Extract, RawRecord

SOURCE = "csv"


def _ts(v: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {v!r}. Export timestamps with an offset.")
    return t.astimezone(dt.UTC)


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _bool(v: str) -> bool:
    return v.lower() in {"1", "true", "yes", "y", "t"}


def extract(folder: Path, default_currency: str = "GBP") -> Extract:
    ex = Extract(source=SOURCE)
    orders = _rows(folder / "orders.csv")
    if not orders:
        raise FileNotFoundError(f"{folder / 'orders.csv'} is missing or empty")
    order_ts: dict[str, dt.datetime] = {}
    for r in orders:
        try:
            ts = _ts(r["created_at"])
        except (KeyError, ValueError):
            ex.drop("orders", "bad_created_at")
            continue
        updated = _ts(r["updated_at"]) if r.get("updated_at") else ts
        order_ts[r["order_id"]] = ts
        ex.rows["orders"].append(
            RawRecord(
                r["order_id"],
                {
                    "order_id": r["order_id"],
                    "customer_id": r.get("customer_id") or None,
                    "email": r.get("email") or None,
                    "created_at": ts.isoformat(),
                    "currency": (r.get("currency") or default_currency).upper(),
                    "status": (r.get("status") or "paid").lower(),
                    "test": _bool(r.get("test", "")),
                    "country": r.get("country") or None,
                    "utm_source": r.get("utm_source") or None,
                    "utm_medium": r.get("utm_medium") or None,
                    "referrer": r.get("referrer") or None,
                    "discount_codes": [c for c in (r.get("discount_codes") or "").split(";") if c],
                },
                updated,
            )
        )

    for r in _rows(folder / "order_items.csv"):
        ts = order_ts.get(r.get("order_id", ""))
        if ts is None:
            ex.drop("order_items", "unknown_order")
            continue
        try:
            qty, price = int(float(r["quantity"])), float(r["unit_price"])
        except (KeyError, ValueError):
            ex.drop("order_items", "bad_number")
            continue
        ex.rows["order_items"].append(
            RawRecord(
                r["line_id"],
                {
                    "line_id": r["line_id"],
                    "order_id": r["order_id"],
                    "sku": r.get("sku") or None,
                    "product_name": r.get("product_name") or None,
                    "category": r.get("category") or None,
                    "quantity": qty,
                    "unit_price": price,
                    "currency": (r.get("currency") or default_currency).upper(),
                    "line_type": (r.get("line_type") or "product").lower(),
                },
                ts,
            )
        )

    for r in _rows(folder / "refunds.csv"):
        try:
            ts = _ts(r["created_at"])
            amount = float(r["amount"])
        except (KeyError, ValueError):
            ex.drop("refunds", "bad_row")
            continue
        ex.rows["refunds"].append(
            RawRecord(
                r["refund_id"],
                {
                    "refund_id": r["refund_id"],
                    "order_id": r["order_id"],
                    "amount": abs(amount),
                    "currency": (r.get("currency") or default_currency).upper(),
                    "created_at": ts.isoformat(),
                },
                ts,
            )
        )

    for r in _rows(folder / "customers.csv"):
        ts = _ts(r["created_at"]) if r.get("created_at") else dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        ex.rows["customers"].append(
            RawRecord(
                r["customer_id"],
                {
                    "customer_id": r["customer_id"],
                    "email": r.get("email") or None,
                    "country": r.get("country") or None,
                    "created_at": ts.isoformat(),
                },
                ts,
            )
        )

    for r in _rows(folder / "spend.csv"):
        ex.spend.append(
            (
                dt.date.fromisoformat(r["date"]),
                r["channel"],
                float(r["spend_amount"]),
                (r.get("currency") or default_currency).upper(),
            )
        )
    return ex


def read_spend(path: Path, default_currency: str) -> list[tuple[dt.date, str, float, str]]:
    """Spend-only upload (Channels page)."""
    return [
        (
            dt.date.fromisoformat(r["date"]),
            r["channel"],
            float(r["spend_amount"]),
            (r.get("currency") or default_currency).upper(),
        )
        for r in _rows(path)
    ]
