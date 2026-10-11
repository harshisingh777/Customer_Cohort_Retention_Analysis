"""Online Retail II: the heatmap must match a separate pandas computation within 0.1 pt (spec §11).

Independent of dbt: starts from the ingest adapter's cleaned rows (cancellations already
allocated to refunds), applies the excluded-lines seed and the qualifying rules in pandas, and
rebuilds cohort cells. Needs the dataset in data/ and takes a couple of minutes (marked slow).
The test database already holds Online Retail II from the session fixture.
"""

import csv
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.db, pytest.mark.slow, pytest.mark.retail]


def _excluded() -> list[tuple[str, str]]:
    with (ROOT / "pipeline/dbt/seeds/excluded_line_codes.csv").open(encoding="utf-8") as f:
        return [
            (r["match_type"], r["code"])
            for r in csv.DictReader(f)
            if r["source"] in ("*", "online_retail_ii")
        ]


def _is_excluded(sku: str, rules) -> bool:
    return any(
        (m == "exact" and sku == c) or (m == "prefix" and sku.startswith(c)) for m, c in rules
    )


def pandas_cells(ex, cutoff) -> dict:
    rules = _excluded()
    orders = pd.DataFrame([{**r.payload} for r in ex.rows["orders"]])
    items = pd.DataFrame([r.payload for r in ex.rows["order_items"]])
    refunds = pd.DataFrame([r.payload for r in ex.rows["refunds"]])
    items = items[~items["sku"].map(lambda s: _is_excluded(s, rules)) & (items["quantity"] > 0)]
    refunds = refunds[~refunds["sku"].map(lambda s: _is_excluded(s, rules))]
    gross = (items["quantity"] * items["unit_price"]).groupby(items["order_id"]).sum()
    ts_local = pd.to_datetime(orders["created_at"], utc=True).dt.tz_convert("Europe/London")
    refunds["day"] = (
        pd.to_datetime(refunds["created_at"], utc=True).dt.tz_convert("Europe/London").dt.date
    )
    refunded = refunds[refunds["day"] < cutoff].groupby("order_id")["amount"].sum()
    orders = orders.assign(ts=ts_local.dt.tz_localize(None), day=ts_local.dt.date)
    # Round to cents: in floats a full refund (10.20 - 10.20) can leave 1e-15 and look "qualifying";
    # the marts use exact numerics.
    net = orders["order_id"].map(gross).fillna(0) - orders["order_id"].map(refunded).fillna(0)
    orders["net"] = net.round(2)
    q = orders[(orders["net"] > 0) & (orders["day"] < cutoff)].copy()
    q["month"] = q["ts"].dt.to_period("M")
    q = q.sort_values(["customer_id", "ts", "order_id"])
    first = q.groupby("customer_id")["month"].first().rename("cohort")
    act = q[["customer_id", "month"]].drop_duplicates().join(first, on="customer_id")
    act["p"] = (act["month"] - act["cohort"]).map(lambda d: d.n)
    last_complete = pd.Period(cutoff, "M") - 1
    sizes = first.value_counts()
    counts = act[act["month"] <= last_complete].groupby(["cohort", "p"]).size()
    out = {}
    for cohort, size in sizes.items():
        if cohort > last_complete:
            continue
        for p in range((last_complete - cohort).n + 1):
            out[(cohort.start_time.date(), p)] = int(counts.get((cohort, p), 0)) / int(size)
    return out


def test_heatmap_matches_pandas(published):
    from core.db import connect
    from pipeline.ingest.datasets import online_retail_ii as ds

    data_dir = ROOT / "data"
    ex = ds.extract(data_dir)
    ex.rows["order_items"] = list(ex.rows["order_items"])
    expected = pandas_cells(ex, ds.as_of_date(ex))
    with connect() as conn:
        rows = conn.execute(
            "select cohort_month, period_number, sum(active_customers)::float / sum(cohort_customers) as rate "
            "from analytics.mart_cohort_retention_monthly group by 1, 2"
        ).fetchall()
    actual = {(r["cohort_month"], r["period_number"]): r["rate"] for r in rows}
    assert set(actual) == set(expected)
    worst = max(abs(actual[k] - expected[k]) for k in expected)
    assert worst * 100 <= 0.1, f"largest difference {worst * 100:.3f} pt"
