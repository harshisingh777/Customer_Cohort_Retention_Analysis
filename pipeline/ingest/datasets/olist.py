# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportOptionalSubscript=false, reportAssignmentType=false
# (pandas-stubs types itertuples() rows as plain tuples and most frame ops as unions.)
"""Olist Brazilian E-Commerce (Kaggle) → raw, canonical payload shape.

The low-repeat stress case (spec §7.2). Identity uses `customer_unique_id`; Olist's
`customer_id` is per order and would make every order a new customer.

Kaggle downloads need an account, so place the CSVs in data/olist/ first:
  olist_orders_dataset.csv, olist_customers_dataset.csv, olist_order_items_dataset.csv,
  olist_products_dataset.csv, product_category_name_translation.csv
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.ingest.core import Extract, RawRecord

SOURCE = "olist"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
STATUS_MAP = {
    "delivered": "delivered",
    "shipped": "shipped",
    "invoiced": "invoiced",
    "processing": "processing",
    "approved": "paid",
    "created": "pending",
    "canceled": "cancelled",
    "unavailable": "cancelled",
}
SETTINGS = {
    "store_name": "Olist (Kaggle demo)",
    "reporting_tz": "America/Sao_Paulo",
    "reporting_currency": "BRL",
    "locale": "pt-BR",
}


def _utc(ts: pd.Timestamp) -> dt.datetime:
    return ts.to_pydatetime().replace(tzinfo=SAO_PAULO).astimezone(dt.UTC)


def extract(data_dir: Path) -> Extract:
    d = data_dir / "olist"
    missing = [
        f
        for f in (
            "olist_orders_dataset.csv",
            "olist_customers_dataset.csv",
            "olist_order_items_dataset.csv",
            "olist_products_dataset.csv",
        )
        if not (d / f).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"Olist files missing in {d}: {', '.join(missing)}. Download them from "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
        )
    orders = pd.read_csv(d / "olist_orders_dataset.csv", parse_dates=["order_purchase_timestamp"])
    customers = pd.read_csv(d / "olist_customers_dataset.csv", dtype=str)
    items = pd.read_csv(d / "olist_order_items_dataset.csv")
    products = pd.read_csv(d / "olist_products_dataset.csv", dtype=str)
    translation_path = d / "product_category_name_translation.csv"
    if translation_path.exists():
        tr = pd.read_csv(translation_path, dtype=str)
        products = products.merge(tr, on="product_category_name", how="left")
        products["category"] = products["product_category_name_english"].fillna(
            products["product_category_name"]
        )
    else:
        products["category"] = products["product_category_name"]
    products["category"] = products["category"].str.replace("_", " ").str.capitalize()

    ex = Extract(source=SOURCE)
    orders = orders.merge(
        customers[["customer_id", "customer_unique_id", "customer_state"]],
        on="customer_id",
        how="left",
    )
    no_id = orders["customer_unique_id"].isna()
    ex.drop("orders", "no_customer_unique_id", int(no_id.sum()))
    orders = orders[~no_id]

    for o in orders.itertuples(index=False):
        ts = _utc(o.order_purchase_timestamp)
        ex.rows["orders"].append(
            RawRecord(
                o.order_id,
                {
                    "order_id": o.order_id,
                    "customer_id": o.customer_unique_id,
                    "email": None,
                    "created_at": ts.isoformat(),
                    "currency": "BRL",
                    "status": STATUS_MAP.get(o.order_status, o.order_status),
                    "test": False,
                    "country": "BR",
                    "region": o.customer_state,
                    "discount_codes": [],
                    "source_order_customer_id": o.customer_id,
                },
                ts,
            )
        )

    firsts = orders.sort_values("order_purchase_timestamp").groupby("customer_unique_id").first()
    for cid, c in firsts.iterrows():
        ts = _utc(c["order_purchase_timestamp"])
        ex.rows["customers"].append(
            RawRecord(
                str(cid),
                {
                    "customer_id": str(cid),
                    "email": None,
                    "country": "BR",
                    "region": c["customer_state"],
                    "created_at": ts.isoformat(),
                },
                ts,
            )
        )

    items = items.merge(products[["product_id", "category"]], on="product_id", how="left")
    order_ts = {
        o.order_id: _utc(o.order_purchase_timestamp) for o in orders.itertuples(index=False)
    }
    for it in items.itertuples(index=False):
        ts = order_ts.get(it.order_id)
        if ts is None:
            ex.drop("order_items", "order_not_loaded")
            continue
        base = f"{it.order_id}-{it.order_item_id}"
        ex.rows["order_items"].append(
            RawRecord(
                base,
                {
                    "line_id": base,
                    "order_id": it.order_id,
                    "sku": it.product_id,
                    "product_name": it.product_id,
                    "category": it.category if isinstance(it.category, str) else None,
                    "quantity": 1,
                    "unit_price": float(it.price),
                    "currency": "BRL",
                    "line_type": "product",
                    "seller_id": it.seller_id,
                },
                ts,
            )
        )
        if float(it.freight_value) > 0:
            ex.rows["order_items"].append(
                RawRecord(
                    f"{base}-F",
                    {
                        "line_id": f"{base}-F",
                        "order_id": it.order_id,
                        "sku": "FREIGHT",
                        "product_name": "Freight",
                        "category": None,
                        "quantity": 1,
                        "unit_price": float(it.freight_value),
                        "currency": "BRL",
                        "line_type": "shipping",
                    },
                    ts,
                )
            )
    return ex


def as_of_date(ex: Extract) -> dt.date:
    last = max(r.source_updated_at for r in ex.rows["orders"])
    return last.astimezone(SAO_PAULO).date() + dt.timedelta(days=1)
