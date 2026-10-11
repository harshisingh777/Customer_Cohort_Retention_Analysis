"""WooCommerce REST API v3 adapter (spec §7.4).

Increments use `modified_after` with a 3-day overlap, `per_page=100`. Refund dates are not in
the order payload, so orders with refunds get their refunds fetched separately.
Self-hosted stores often add plugin statuses: map them in the qualifying-status setting.
"""

from __future__ import annotations

import datetime as dt
import time

import httpx

from pipeline.ingest.core import Extract, RawRecord

SOURCE = "woocommerce"
OVERLAP = dt.timedelta(days=3)


def _gmt(v: str | None) -> dt.datetime:
    if not v:
        return dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
    return dt.datetime.fromisoformat(v).replace(tzinfo=dt.UTC)


class WooClient:
    def __init__(self, base_url: str, key: str, secret: str) -> None:
        self.http = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/wp-json/wc/v3", auth=(key, secret), timeout=60
        )

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        for attempt in range(6):
            r = self.http.get(path, params=params)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2**attempt)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"WooCommerce kept failing on {path}")

    def paged(self, path: str, params: dict) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            r = self.get(path, {**params, "per_page": 100, "page": page})
            batch = r.json()
            out.extend(batch)
            if page >= int(r.headers.get("X-WP-TotalPages", "1")) or not batch:
                return out
            page += 1


def extract(base_url: str, key: str, secret: str, cursor: str | None) -> Extract:
    client = WooClient(base_url, key, secret)
    ex = Extract(source=SOURCE)
    params: dict = {"orderby": "modified", "order": "asc", "dates_are_gmt": "true"}
    if cursor:
        params["modified_after"] = (dt.datetime.fromisoformat(cursor) - OVERLAP).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    newest = dt.datetime.fromisoformat(cursor) if cursor else dt.datetime(1970, 1, 1, tzinfo=dt.UTC)

    for o in client.paged("/orders", params):
        updated = _gmt(o.get("date_modified_gmt"))
        newest = max(newest, updated)
        oid = str(o["id"])
        ex.rows["orders"].append(
            RawRecord(oid, {k: v for k, v in o.items() if k != "line_items"}, updated)
        )
        for ln in o.get("line_items") or []:
            ex.rows["order_items"].append(
                RawRecord(
                    str(ln["id"]), {**ln, "order_id": oid, "currency": o.get("currency")}, updated
                )
            )
        if o.get("refunds"):
            for rf in client.get(f"/orders/{oid}/refunds").json():
                ts = _gmt(rf.get("date_created_gmt"))
                ex.rows["refunds"].append(
                    RawRecord(
                        str(rf["id"]), {**rf, "order_id": oid, "currency": o.get("currency")}, ts
                    )
                )

    cparams: dict = {"orderby": "registered_date", "order": "asc"}
    for c in client.paged("/customers", cparams):
        ts = _gmt(c.get("date_modified_gmt") or c.get("date_created_gmt"))
        ex.rows["customers"].append(RawRecord(str(c["id"]), c, ts))

    ex.cursors["orders"] = newest.isoformat()
    return ex
