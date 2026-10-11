"""Shopify GraphQL Admin API adapter (spec §7.4).

- Backfill: a bulk operation (JSONL) over all orders.
- Daily: paginated orders query on updated_at, from the stored cursor minus a 3-day overlap
  so late refunds restate the orders they belong to.

Raw rows keep Shopify's native payloads. `stg_*` extracts typed columns from them.
Needs the `read_orders`, `read_all_orders` and `read_customers` scopes; without
`read_all_orders` only the last 60 days are visible.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Iterator

import httpx

from pipeline.ingest.core import Extract, RawRecord

log = logging.getLogger(__name__)

SOURCE = "shopify"
API_VERSION = "2025-07"
OVERLAP = dt.timedelta(days=3)

ORDER_FIELDS = """
  id name createdAt updatedAt cancelledAt test displayFinancialStatus email currencyCode
  customer { id email createdAt updatedAt }
  shippingAddress { countryCodeV2 }
  billingAddress { countryCodeV2 }
  discountCodes
  customerJourneySummary { firstVisit { referrerUrl utmParameters { source medium campaign } } }
  refunds { id createdAt totalRefundedSet { shopMoney { amount currencyCode } } }
"""
LINE_FIELDS = """
  id sku name quantity
  originalUnitPriceSet { shopMoney { amount currencyCode } }
  discountedUnitPriceAfterAllDiscountsSet { shopMoney { amount currencyCode } }
  product { productType }
"""

PAGE_QUERY = f"""
query Orders($cursor: String, $q: String!) {{
  orders(first: 50, after: $cursor, query: $q, sortKey: UPDATED_AT) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{ {ORDER_FIELDS} lineItems(first: 100) {{ nodes {{ {LINE_FIELDS} }} }} }}
  }}
}}
"""

BULK_QUERY = f"""
mutation {{
  bulkOperationRunQuery(query: \"\"\"
    {{ orders {{ edges {{ node {{ {ORDER_FIELDS} lineItems {{ edges {{ node {{ {LINE_FIELDS} }} }} }} }} }} }} }}
  \"\"\") {{ bulkOperation {{ id status }} userErrors {{ field message }} }}
}}
"""

BULK_STATUS = "{ currentBulkOperation { id status errorCode objectCount url } }"


class ShopifyClient:
    def __init__(self, shop: str, token: str) -> None:
        self.http = httpx.Client(
            base_url=f"https://{shop}/admin/api/{API_VERSION}",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            timeout=60,
        )

    def gql(self, query: str, variables: dict | None = None) -> dict:
        for attempt in range(6):
            r = self.http.post("/graphql.json", json={"query": query, "variables": variables or {}})
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2**attempt)
                continue
            r.raise_for_status()
            body = r.json()
            errors = body.get("errors")
            if errors and any(e.get("extensions", {}).get("code") == "THROTTLED" for e in errors):
                time.sleep(2**attempt)
                continue
            if errors:
                raise RuntimeError(f"Shopify GraphQL error: {errors}")
            return body["data"]
        raise RuntimeError("Shopify API kept throttling; giving up after 6 attempts")


def _order_records(order: dict, lines: list[dict], ex: Extract) -> None:
    oid = order["id"]
    updated = dt.datetime.fromisoformat(order["updatedAt"].replace("Z", "+00:00"))
    ex.rows["orders"].append(
        RawRecord(oid, {k: v for k, v in order.items() if k != "lineItems"}, updated)
    )
    for ln in lines:
        ex.rows["order_items"].append(RawRecord(ln["id"], {**ln, "order_id": oid}, updated))
    for rf in order.get("refunds") or []:
        ts = dt.datetime.fromisoformat(rf["createdAt"].replace("Z", "+00:00"))
        ex.rows["refunds"].append(RawRecord(rf["id"], {**rf, "order_id": oid}, ts))
    c = order.get("customer")
    if c and c.get("id"):
        cts = dt.datetime.fromisoformat(
            (c.get("updatedAt") or order["updatedAt"]).replace("Z", "+00:00")
        )
        ex.rows["customers"].append(RawRecord(c["id"], c, cts))


def incremental(client: ShopifyClient, since: dt.datetime) -> Extract:
    ex = Extract(source=SOURCE)
    q = f"updated_at:>='{(since - OVERLAP).strftime('%Y-%m-%dT%H:%M:%SZ')}'"
    cursor = None
    newest = since
    while True:
        data = client.gql(PAGE_QUERY, {"cursor": cursor, "q": q})["orders"]
        for node in data["nodes"]:
            _order_records(node, node["lineItems"]["nodes"], ex)
            newest = max(
                newest, dt.datetime.fromisoformat(node["updatedAt"].replace("Z", "+00:00"))
            )
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    ex.cursors["orders"] = newest.isoformat()
    return ex


def _bulk_lines(url: str) -> Iterator[dict]:
    with httpx.stream("GET", url, timeout=600) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.strip():
                yield json.loads(line)


def backfill(client: ShopifyClient, poll_seconds: float = 10) -> Extract:
    result = client.gql(BULK_QUERY)["bulkOperationRunQuery"]
    if result["userErrors"]:
        raise RuntimeError(f"bulk operation rejected: {result['userErrors']}")
    while True:
        op = client.gql(BULK_STATUS)["currentBulkOperation"]
        if op["status"] in {"COMPLETED", "FAILED", "CANCELED", "EXPIRED"}:
            break
        time.sleep(poll_seconds)
    if op["status"] != "COMPLETED":
        raise RuntimeError(f"bulk operation {op['status']}: {op.get('errorCode')}")
    ex = Extract(source=SOURCE)
    if not op.get("url"):
        return ex
    orders: dict[str, dict] = {}
    lines: dict[str, list[dict]] = {}
    for obj in _bulk_lines(op["url"]):
        parent = obj.pop("__parentId", None)
        if parent:
            lines.setdefault(parent, []).append(obj)
        else:
            orders[obj["id"]] = obj
    newest = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
    for oid, order in orders.items():
        _order_records(order, lines.get(oid, []), ex)
        newest = max(newest, dt.datetime.fromisoformat(order["updatedAt"].replace("Z", "+00:00")))
    ex.cursors["orders"] = newest.isoformat()
    return ex


def extract(shop: str, token: str, cursor: str | None) -> Extract:
    client = ShopifyClient(shop, token)
    if cursor is None:
        log.info("shopify backfill via bulk operation")
        return backfill(client)
    return incremental(client, dt.datetime.fromisoformat(cursor))
