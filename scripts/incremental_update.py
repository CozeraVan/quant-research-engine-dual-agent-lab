#!/usr/bin/env python
"""Daily incremental backtest update (P1).

For each subscribed strategy (catalog YAML), resume from its checkpoint at
``outputs/state/<strategy_id>/`` and process only new bars up to the data
watermark. One strategy's failure never blocks the others.

Usage:
    uv run python scripts/incremental_update.py --strategy all
    uv run python scripts/incremental_update.py --strategy mr04a_ibs_reversal --dry-run
    uv run python scripts/incremental_update.py --strategy all --codes 000001.SZ 600519.SH
    uv run python scripts/incremental_update.py --strategy all --date 2026-07-24
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_research_engine.orchestration.batch_runner import discover_strategies
from quant_research_engine.orchestration.incremental import (
    IncrementalRequest,
    run_incremental,
)
from quant_research_engine.strategies.spec import StrategySpec


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _build_store():
    from quant_research_engine.data.postgres import PostgresDataStore
    from quant_research_engine.data.settings import DatabaseSettings

    store = PostgresDataStore(DatabaseSettings.from_env())
    store.ping()
    return store


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily incremental backtest update")
    parser.add_argument("--strategy", required=True, help="strategy id or 'all'")
    parser.add_argument("--codes", nargs="*", default=None, help="restrict symbols")
    parser.add_argument("--date", default=None, help="override watermark (YYYY-MM-DD)")
    parser.add_argument("--start", default="2015-01-01", help="bootstrap start (default 2015-01-01)")
    parser.add_argument("--end", default=None, help="window end cap (default: watermark date)")
    parser.add_argument("--catalog", default=str(PROJECT_ROOT / "strategies" / "catalog"))
    parser.add_argument("--output-root", default=str(PROJECT_ROOT / "outputs" / "state"))
    parser.add_argument("--initial-cash", type=float, default=1_000_000)
    parser.add_argument("--apply-stops", action="store_true")
    parser.add_argument("--universe-filter", action="store_true")
    parser.add_argument("--warmup-days", type=int, default=150)
    parser.add_argument("--dry-run", action="store_true", help="show watermark/window only")
    args = parser.parse_args()

    catalog_dir = Path(args.catalog)
    if args.strategy == "all":
        yaml_paths = discover_strategies(catalog_dir)
    else:
        yaml_paths = discover_strategies(catalog_dir, strategy_ids=[args.strategy])
    if not yaml_paths:
        print(f"No strategy YAML found for: {args.strategy}")
        return 1

    output_root = Path(args.output_root)
    start = _parse_date(args.start)
    end = _parse_date(args.end) if args.end else date.today()
    watermark_override = _parse_date(args.date) if args.date else None

    store = _build_store()
    try:
        rows = []
        failures = 0
        for yaml_path in yaml_paths:
            strategy_id = yaml_path.stem
            try:
                spec = StrategySpec.from_yaml(yaml_path)
                request = IncrementalRequest(
                    strategy_path=yaml_path,
                    start=start,
                    end=end,
                    output_root=output_root,
                    initial_cash=args.initial_cash,
                    apply_stops=args.apply_stops,
                    universe_filter=args.universe_filter,
                    codes=args.codes,
                    warmup_days=args.warmup_days,
                    watermark=watermark_override,
                )
                if args.dry_run:
                    from quant_research_engine.orchestration.incremental_state import (
                        load_checkpoint,
                    )
                    from quant_research_engine.orchestration.refresh import data_watermark

                    checkpoint = load_checkpoint(output_root / strategy_id / "state.json")
                    watermark = watermark_override or data_watermark(store)
                    last = checkpoint.last_processed_date if checkpoint else None
                    window = f"{last} -> {watermark}" if last else f"bootstrap {start} -> {watermark}"
                    rows.append((strategy_id, "dry-run", window, 0.0))
                    continue
                result = run_incremental(store, spec, request)
                new_total = sum(result.new_rows.values())
                status = "updated" if result.updated else "no-op"
                rows.append((strategy_id, status, f"+{new_total} rows", result.duration_s))
            except Exception as exc:  # one failure never blocks the rest
                failures += 1
                rows.append((strategy_id, "ERROR", str(exc)[:80], 0.0))

        print(f"\n{'strategy':45s} {'status':10s} {'detail':40s} {'time':>8s}")
        print("-" * 110)
        for strategy_id, status, detail, duration in rows:
            print(f"{strategy_id:45s} {status:10s} {detail:40s} {duration:7.1f}s")
        return 1 if failures else 0
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    sys.exit(main())
