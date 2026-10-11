"""Ingest CLI.

python -m pipeline.ingest seed retail|olist [--skip-clv] [--keep-raw]
python -m pipeline.ingest csv <folder>
python -m pipeline.ingest spend <spend.csv>
python -m pipeline.ingest live
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.config import get_env
from core.db import connect, read_store_settings
from core.logging import setup_logging
from pipeline.ingest.adapters import csv_drop
from pipeline.ingest.core import Extract, ensure_raw_schema, write_extract
from pipeline.ingest.run import DATASETS, ingest_live, load_dataset


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="pipeline.ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="load a public dataset, then refresh and publish")
    s.add_argument("dataset", choices=DATASETS)
    s.add_argument("--skip-clv", action="store_true")
    s.add_argument("--keep-raw", action="store_true", help="don't truncate raw first")
    c = sub.add_parser("csv", help="load a folder of canonical CSV files")
    c.add_argument("folder", type=Path)
    sp = sub.add_parser(
        "spend", help="load marketing spend (date, channel, spend_amount, currency)"
    )
    sp.add_argument("file", type=Path)
    sub.add_parser("live", help="pull configured platforms (Shopify, WooCommerce)")
    args = ap.parse_args(argv)

    env = get_env()
    with connect() as conn:
        ensure_raw_schema(conn)
        if args.cmd == "seed":
            stats = load_dataset(conn, args.dataset, Path(env.data_dir), reset=not args.keep_raw)
        elif args.cmd == "csv":
            settings = read_store_settings(conn)
            stats = write_extract(conn, csv_drop.extract(args.folder, settings.reporting_currency))
        elif args.cmd == "spend":
            settings = read_store_settings(conn)
            ex = Extract(source="csv")
            ex.spend = csv_drop.read_spend(args.file, settings.reporting_currency)
            stats = write_extract(conn, ex)
        else:
            stats = ingest_live(conn)
    print(json.dumps({"ingest": stats}, default=str, indent=2))

    if args.cmd == "seed":
        from pipeline.worker.refresh import run_refresh

        result = run_refresh(trigger=f"seed:{args.dataset}", skip_ingest=True)
        print(json.dumps({"refresh": result}, default=str, indent=2))
        if result["status"] != "published":
            return 1
        if not args.skip_clv:
            from pipeline.clv.fit import run_clv_fit

            clv = run_clv_fit(trigger=f"seed:{args.dataset}")
            print(json.dumps({"clv": clv}, default=str, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
