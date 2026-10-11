# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportOptionalSubscript=false, reportAssignmentType=false
# (pandas-stubs types itertuples() rows as plain tuples and most frame ops as unions.)
"""Online Retail II (UCI dataset 502) → raw, in the canonical payload shape.

Cleaning rules (spec §7.1):
- Rows without a Customer ID are dropped from customer metrics; the dropped share is recorded
  in ops.ingest_batches and shown on the Data page, because it biases retention upward.
- Invoices starting with "C" are cancellations. Each cancelled quantity is allocated to the same
  customer's earlier purchases of the same stock code, most recent first, and becomes a refund
  against those invoices. Quantity that can't be matched is dropped and counted.
- Non-product stock codes (postage, manual adjustments, bank charges, fees) are kept in raw and
  excluded by the dbt seed `excluded_line_codes`.
- InvoiceDate is UK local time; it is stored as UTC and re-bucketed in the reporting timezone.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.ingest.core import Extract, RawRecord

log = logging.getLogger(__name__)

SOURCE = "online_retail_ii"
URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
LONDON = ZoneInfo("Europe/London")
SETTINGS = {
    "store_name": "Online Retail II (UCI demo)",
    "reporting_tz": "Europe/London",
    "reporting_currency": "GBP",
    "locale": "en-GB",
}


def locate(data_dir: Path) -> Path:
    for name in ("online_retail_II.xlsx", "online_retail_ii.xlsx", "online_retail_II.csv"):
        if (data_dir / name).exists():
            return data_dir / name
    zip_path = data_dir / "online_retail_ii.zip"
    if not zip_path.exists():
        import httpx

        data_dir.mkdir(parents=True, exist_ok=True)
        log.info("downloading dataset", extra={"url": URL})
        with httpx.stream("GET", URL, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with zip_path.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    import zipfile

    with zipfile.ZipFile(zip_path) as z:
        z.extractall(data_dir)
    return data_dir / "online_retail_II.xlsx"


def read_frame(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        df = pd.read_csv(path, dtype={"Invoice": str, "StockCode": str})
    else:
        sheets = pd.read_excel(path, sheet_name=None, dtype={"Invoice": str, "StockCode": str})
        frames = list(sheets.values())
        # The two yearly sheets overlap in early December 2010. Keep each invoice from one sheet.
        seen: set[str] = set()
        kept = []
        for f in frames:
            f = f[~f["Invoice"].isin(seen)]
            seen |= set(f["Invoice"])
            kept.append(f)
        df = pd.concat(kept, ignore_index=True)
    df = df.rename(columns={"Customer ID": "CustomerID"})
    df["Invoice"] = df["Invoice"].astype(str).str.strip()
    df["StockCode"] = df["StockCode"].astype(str).str.strip()
    df["Description"] = df["Description"].fillna("").astype(str).str.strip()
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return df


def _to_utc(ts: pd.Timestamp) -> dt.datetime:
    return ts.to_pydatetime().replace(tzinfo=LONDON).astimezone(dt.UTC)


def build_extract(df: pd.DataFrame) -> Extract:
    ex = Extract(source=SOURCE)
    n_total = len(df)

    no_cust = df["CustomerID"].isna()
    ex.drop("order_items", "no_customer_id", int(no_cust.sum()))
    df = df[~no_cust].copy()
    df["CustomerID"] = df["CustomerID"].astype(int).astype(str)

    is_cancel = df["Invoice"].str.startswith("C")
    bad_debt = df["Invoice"].str.startswith("A")
    ex.drop("order_items", "bad_debt_adjustment", int(bad_debt.sum()))
    sales = df[~is_cancel & ~bad_debt]
    cancels = df[is_cancel]

    non_positive = (sales["Quantity"] <= 0) | (sales["Price"] <= 0)
    ex.drop("order_items", "non_positive_quantity_or_price", int(non_positive.sum()))
    sales = sales[~non_positive].copy()
    sales["line_no"] = sales.groupby("Invoice").cumcount() + 1

    # Orders and items ------------------------------------------------------------------
    headers = sales.groupby("Invoice", sort=False).agg(
        CustomerID=("CustomerID", "first"),
        InvoiceDate=("InvoiceDate", "min"),
        Country=("Country", "first"),
    )
    for inv, h in headers.iterrows():
        ts = _to_utc(h["InvoiceDate"])
        ex.rows["orders"].append(
            RawRecord(
                str(inv),
                {
                    "order_id": str(inv),
                    "customer_id": h["CustomerID"],
                    "email": None,
                    "created_at": ts.isoformat(),
                    "currency": "GBP",
                    "status": "paid",
                    "test": False,
                    "country": h["Country"],
                    "discount_codes": [],
                },
                ts,
            )
        )

    def items(frame: pd.DataFrame):
        # Streamed: ~800k lines. Every source column is kept, under canonical names
        # (Invoice→order_id, StockCode→sku, Description→product_name, Price→unit_price).
        for row in frame.itertuples(index=False):
            line_id = f"{row.Invoice}-{row.line_no}"
            yield RawRecord(
                line_id,
                {
                    "line_id": line_id,
                    "order_id": row.Invoice,
                    "sku": row.StockCode,
                    "product_name": row.Description,
                    "category": None,
                    "quantity": int(row.Quantity),
                    "unit_price": float(row.Price),
                    "currency": "GBP",
                    "line_type": "product",
                },
                _to_utc(row.InvoiceDate),
            )

    ex.rows["order_items"] = items(sales)  # type: ignore[assignment]
    n_items = len(sales)

    # Customers: first seen country and timestamp ------------------------------------------
    firsts = headers.sort_values("InvoiceDate").groupby("CustomerID").first()
    for cid, c in firsts.iterrows():
        ts = _to_utc(c["InvoiceDate"])
        ex.rows["customers"].append(
            RawRecord(
                str(cid),
                {
                    "customer_id": str(cid),
                    "email": None,
                    "country": c["Country"],
                    "created_at": ts.isoformat(),
                },
                ts,
            )
        )

    # Cancellations → refunds ---------------------------------------------------------------
    # Available quantity per (customer, stock code), newest purchase first.
    avail: dict[tuple[str, str], list[list]] = defaultdict(list)
    for row in sales.sort_values("InvoiceDate").itertuples(index=False):
        avail[(row.CustomerID, row.StockCode)].append(
            [row.InvoiceDate, row.Invoice, int(row.Quantity)]
        )

    unmatched = 0
    refund_seq: dict[str, int] = defaultdict(int)
    for row in cancels.sort_values("InvoiceDate").itertuples(index=False):
        qty = abs(int(row.Quantity))
        price = abs(float(row.Price))
        if qty == 0 or price == 0:
            continue
        lots = avail.get((row.CustomerID, row.StockCode), [])
        for lot in reversed(lots):
            if qty == 0:
                break
            bought_at, invoice, remaining = lot
            if remaining <= 0 or bought_at > row.InvoiceDate:
                continue
            take = min(qty, remaining)
            lot[2] -= take
            qty -= take
            refund_seq[row.Invoice] += 1
            rid = f"{row.Invoice}-{refund_seq[row.Invoice]}"
            ts = _to_utc(row.InvoiceDate)
            ex.rows["refunds"].append(
                RawRecord(
                    rid,
                    {
                        "refund_id": rid,
                        "order_id": invoice,
                        "amount": round(take * price, 2),
                        "currency": "GBP",
                        "created_at": ts.isoformat(),
                        "sku": row.StockCode,
                        "cancellation_invoice": row.Invoice,
                        "quantity": take,
                    },
                    ts,
                )
            )
        if qty > 0:
            unmatched += 1
    ex.drop("refunds", "cancellation_without_matching_purchase", unmatched)

    log.info(
        "online retail ii extract",
        extra={
            "rows_total": n_total,
            "orders": len(ex.rows["orders"]),
            "items": n_items,
            "refunds": len(ex.rows["refunds"]),
            "customers": len(ex.rows["customers"]),
        },
    )
    return ex


def as_of_date(ex: Extract) -> dt.date:
    """The day after the last invoice, in UK local time."""
    last = max(r.source_updated_at for r in ex.rows["orders"])
    return last.astimezone(LONDON).date() + dt.timedelta(days=1)


def extract(data_dir: Path) -> Extract:
    return build_extract(read_frame(locate(data_dir)))
