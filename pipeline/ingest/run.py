"""Entry points used by the worker (live sources) and the seed CLI (datasets)."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from core.config import get_env
from core.db import Conn, read_store_settings
from pipeline.ingest.core import Extract, ensure_raw_schema, read_cursor, write_extract
from pipeline.ingest.fx import refresh_fx

log = logging.getLogger(__name__)

DATASETS = ("retail", "olist")


def ingest_live(conn: Conn) -> dict:
    """Pull every configured platform from its stored cursor. A no-op for static demos."""
    env = get_env()
    settings = read_store_settings(conn)
    ensure_raw_schema(conn)
    stats: dict = {}
    if env.shopify_shop and env.shopify_access_token:
        from pipeline.ingest.adapters import shopify

        ex = shopify.extract(
            env.shopify_shop, env.shopify_access_token, read_cursor(conn, shopify.SOURCE, "orders")
        )
        stats["shopify"] = write_extract(conn, ex)
    if env.woo_base_url and env.woo_consumer_key:
        from pipeline.ingest.adapters import woocommerce

        ex = woocommerce.extract(
            env.woo_base_url,
            env.woo_consumer_key,
            env.woo_consumer_secret,
            read_cursor(conn, woocommerce.SOURCE, "orders"),
        )
        stats["woocommerce"] = write_extract(conn, ex)
    today = dt.datetime.now(settings.tz).date()
    stats["fx"] = refresh_fx(conn, settings.reporting_currency, today=settings.as_of_date or today)
    return stats


def write_settings(conn: Conn, values: dict, actor: str) -> None:
    for key, value in values.items():
        conn.execute(
            """
            insert into ops.settings (key, value, updated_by) values (%s, %s, %s)
            on conflict (key) do update set value = excluded.value, updated_at = now(),
              updated_by = excluded.updated_by
            """,
            (key, json.dumps(value, default=str), actor),
        )
    conn.execute(
        "insert into ops.audit_log (actor, action, detail) values (%s, 'settings.update', %s)",
        (actor, json.dumps(values, default=str)),
    )
    conn.commit()


def reset_raw(conn: Conn) -> None:
    """Switching demo datasets: start from an empty raw layer."""
    conn.execute(
        "truncate raw.customers, raw.orders, raw.order_items, raw.refunds, raw.marketing_spend, "
        "raw.fx_rates, raw.clv_runs, raw.clv_predictions, raw.clv_holdout, raw.clv_group_draws"
    )
    conn.execute("delete from ops.ingest_cursors")
    conn.execute("delete from ops.ingest_batches")
    conn.commit()


def load_dataset(conn: Conn, name: str, data_dir: Path, *, reset: bool = True) -> dict:
    ensure_raw_schema(conn)
    if reset:
        reset_raw(conn)
    ex: Extract
    if name == "retail":
        from pipeline.ingest.datasets import online_retail_ii as ds

        ex = ds.extract(data_dir)
        settings = {**ds.SETTINGS, "as_of_date": ds.as_of_date(ex).isoformat()}
    elif name == "olist":
        from pipeline.ingest.datasets import olist as ds

        ex = ds.extract(data_dir)
        settings = {
            **ds.SETTINGS,
            "as_of_date": ds.as_of_date(ex).isoformat(),
            "qualifying_statuses": ["paid", "processing", "invoiced", "shipped", "delivered"],
        }
    else:
        raise ValueError(f"unknown dataset {name!r}; choose one of {', '.join(DATASETS)}")
    write_settings(conn, settings, actor=f"seed:{name}")
    stats = write_extract(conn, ex)
    log.info("dataset loaded", extra={"dataset": name, "stats": stats})
    return stats
