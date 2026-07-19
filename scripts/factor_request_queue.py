#!/usr/bin/env python3
"""Missing-factor request queue CLI (upstream handoff for indicators_tushare).

Usage:
  uv run python scripts/factor_request_queue.py list                 # all entries
  uv run python scripts/factor_request_queue.py list --pending       # pending only
  uv run python scripts/factor_request_queue.py show --strategy bo02_keltner_breakout
  uv run python scripts/factor_request_queue.py recheck              # mark fulfilled via DB schema
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.strategies.factor_request_queue import (
    load_queue,
    make_schema_column_lookup,
    recheck_fulfillment,
    save_queue,
)

QUEUE_PATH = ROOT / "outputs" / "handoff" / "missing_factor_requests.json"


def _print_entries(entries, title):
    print(f"{title} ({len(entries)}):")
    for e in entries:
        print(
            f"  [{e.get('status')}] {e.get('strategy_id')} → "
            f"{e.get('expected_table')}.{e.get('expected_column')} "
            f"({e.get('indicator')}, period={e.get('period')}, first_seen={e.get('first_seen', '-')[:10]})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queue-file", type=Path, default=QUEUE_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", help="List queue entries")
    p_list.add_argument("--pending", action="store_true")
    p_list.add_argument("--fulfilled", action="store_true")
    p_show = sub.add_parser("show", help="Show entries for one strategy")
    p_show.add_argument("--strategy", required=True)
    sub.add_parser("recheck", help="Re-check fulfillment against the DB schema (read-only)")
    args = parser.parse_args()

    entries = load_queue(args.queue_file)

    if args.command == "list":
        shown = entries
        if args.pending:
            shown = [e for e in shown if e.get("status") == "pending"]
        if args.fulfilled:
            shown = [e for e in shown if e.get("status") == "fulfilled"]
        _print_entries(shown, f"queue {args.queue_file}")
        return 0

    if args.command == "show":
        shown = [e for e in entries if e.get("strategy_id") == args.strategy]
        _print_entries(shown, f"strategy {args.strategy}")
        return 0 if shown else 1

    if args.command == "recheck":
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.data.settings import DatabaseSettings

        store = PostgresDataStore(DatabaseSettings.from_env())
        lookup = make_schema_column_lookup(store)
        stats = recheck_fulfillment(entries, lookup)
        save_queue(args.queue_file, entries)
        close = getattr(store, "close", None)
        if callable(close):
            close()
        print(
            f"recheck: {stats['newly_fulfilled']} newly fulfilled, "
            f"{stats['pending']} pending, {stats['fulfilled']} fulfilled total"
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
