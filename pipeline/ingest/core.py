"""Idempotent upsert into raw.* and per-batch bookkeeping.

Rule (spec §5.1): insert, or update only when the incoming source_updated_at is newer.
Re-running any batch is therefore a no-op.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from psycopg import sql

from core.db import Conn

ENTITIES = ("customers", "orders", "order_items", "refunds")
RAW_DDL = Path(__file__).with_name("raw_schema.sql")


@dataclass(slots=True)
class RawRecord:
    source_id: str
    payload: dict
    source_updated_at: dt.datetime


@dataclass
class Extract:
    """What an adapter returns: rows per entity plus why anything was dropped."""

    source: str
    # Lists, or generators for very large entities (consumed once by write_extract).
    rows: dict[str, list[RawRecord]] = field(default_factory=lambda: {e: [] for e in ENTITIES})
    dropped: dict[str, Counter] = field(default_factory=lambda: {e: Counter() for e in ENTITIES})
    spend: list[tuple[dt.date, str, float, str]] = field(default_factory=list)
    fx: list[tuple[dt.date, str, str, float]] = field(default_factory=list)
    cursors: dict[str, str] = field(default_factory=dict)

    def drop(self, entity: str, reason: str, n: int = 1) -> None:
        self.dropped[entity][reason] += n


def ensure_raw_schema(conn: Conn) -> None:
    conn.execute(sql.SQL(RAW_DDL.read_text(encoding="utf-8")))  # type: ignore[arg-type]  # trusted file
    conn.commit()


def _json_default(o: object) -> str:
    if isinstance(o, dt.datetime | dt.date):
        return o.isoformat()
    return str(o)


def upsert(
    conn: Conn,
    entity: str,
    source: str,
    records: Iterable[RawRecord],
    batch_id: uuid.UUID,
) -> tuple[int, int]:
    """Stage rows with COPY, then merge. Returns (rows_in, rows_upserted)."""
    if entity not in ENTITIES:
        raise ValueError(f"unknown raw entity {entity!r}")
    rows_in = 0
    with conn.cursor() as cur:
        cur.execute(
            "create temp table if not exists _stage "
            "(source_id text, payload jsonb, source_updated_at timestamptz) on commit drop"
        )
        cur.execute("truncate _stage")
        with cur.copy("copy _stage (source_id, payload, source_updated_at) from stdin") as copy:
            for r in records:
                copy.write_row(
                    (r.source_id, json.dumps(r.payload, default=_json_default), r.source_updated_at)
                )
                rows_in += 1
        table = sql.Identifier("raw", entity)
        cur.execute(
            sql.SQL("""
            insert into {table} (source, source_id, payload, source_updated_at, _batch_id)
            select distinct on (source_id) %(source)s, source_id, payload, source_updated_at, %(batch)s
            from _stage
            order by source_id, source_updated_at desc
            on conflict (source, source_id) do update
              set payload = excluded.payload,
                  source_updated_at = excluded.source_updated_at,
                  _batch_id = excluded._batch_id,
                  _ingested_at = now()
              where excluded.source_updated_at > {table}.source_updated_at
            """).format(table=table),
            {"source": source, "batch": batch_id},
        )
        upserted = cur.rowcount
    return rows_in, upserted


def write_extract(conn: Conn, ex: Extract) -> dict[str, dict]:
    """Write one adapter's extract. Each entity commits with its batch row; cursors advance last."""
    stats: dict[str, dict] = {}
    for entity in ENTITIES:
        records = ex.rows[entity]
        dropped = ex.dropped[entity]
        if isinstance(records, list) and not records and not dropped:
            continue
        batch_id = uuid.uuid4()
        rows_in, upserted = upsert(conn, entity, ex.source, records, batch_id)
        n_dropped = sum(dropped.values())
        conn.execute(
            """
            insert into ops.ingest_batches
              (batch_id, source, entity, finished_at, rows_in, rows_upserted, rows_dropped, drop_reasons)
            values (%s, %s, %s, now(), %s, %s, %s, %s)
            """,
            (
                batch_id,
                ex.source,
                entity,
                rows_in + n_dropped,
                upserted,
                n_dropped,
                json.dumps(dict(dropped)),
            ),
        )
        conn.commit()
        stats[entity] = {"rows_in": rows_in, "upserted": upserted, "dropped": dict(dropped)}

    if ex.spend:
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into raw.marketing_spend (date, channel, spend_amount, currency)
                values (%s, %s, %s, %s)
                on conflict (date, channel) do update
                  set spend_amount = excluded.spend_amount, currency = excluded.currency,
                      _ingested_at = now()
                """,
                ex.spend,
            )
        conn.commit()
        stats["marketing_spend"] = {"rows_in": len(ex.spend)}

    if ex.fx:
        upsert_fx(conn, ex.fx)
        stats["fx_rates"] = {"rows_in": len(ex.fx)}

    for entity, value in ex.cursors.items():
        conn.execute(
            """
            insert into ops.ingest_cursors (source, entity, cursor_value) values (%s, %s, %s)
            on conflict (source, entity) do update
              set cursor_value = excluded.cursor_value, updated_at = now()
            """,
            (ex.source, entity, value),
        )
    conn.commit()
    return stats


def upsert_fx(conn: Conn, rows: list[tuple[dt.date, str, str, float]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into raw.fx_rates (date, base, quote, rate) values (%s, %s, %s, %s)
            on conflict (date, base, quote) do update set rate = excluded.rate
            """,
            rows,
        )
    conn.commit()


def read_cursor(conn: Conn, source: str, entity: str) -> str | None:
    row = conn.execute(
        "select cursor_value from ops.ingest_cursors where source = %s and entity = %s",
        (source, entity),
    ).fetchone()
    return row["cursor_value"] if row else None  # type: ignore[index]
