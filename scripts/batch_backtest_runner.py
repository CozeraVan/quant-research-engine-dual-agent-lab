#!/usr/bin/env python3
"""Batch backtest runner for all strategy catalog YAMLs.

Thin CLI wrapper around `quant_research_engine.orchestration.batch_runner`.

Usage:
  uv run python scripts/batch_backtest_runner.py                    # run all
  uv run python scripts/batch_backtest_runner.py --category mean_reversion
  uv run python scripts/batch_backtest_runner.py --strategies tf01a rsi2
  uv run python scripts/batch_backtest_runner.py --start 2020-01-01 --end 2024-12-31
  uv run python scripts/batch_backtest_runner.py --mode smoke       # 2-month smoke
  uv run python scripts/batch_backtest_runner.py --mode full        # full history
  uv run python scripts/batch_backtest_runner.py --jobs 4           # parallel workers
  uv run python scripts/batch_backtest_runner.py --compact          # slim per-strategy outputs
  uv run python scripts/batch_backtest_runner.py --skip-preflight   # skip DB check
  uv run python scripts/batch_backtest_runner.py --resume           # skip completed
  uv run python scripts/batch_backtest_runner.py --max-strategies 10

Modes:
  smoke   — 2-month window, fast validation (default)
  quick   — 1-year window, 2024 only
  full    — Full date range, heavy computation

Outputs:
  outputs/backtests/{run_batch_id}/
    batch_summary.json              — master summary of all strategies
    {strategy_id}/
      research_run_manifest.json
      report_manifest.json
      preflight/preflight_report.json
      eval/...                      — evaluation artifacts
      backtest/...                  — backtest artifacts (per-symbol tree unless --compact)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.orchestration.batch_runner import (
    MODE_CONFIGS,
    BatchRunConfig,
    BatchSummary,
    completed_strategies,
    discover_strategies,
    execute_batch,
    new_batch_id,
    summarize_results,
    utc_now_iso,
    write_batch_summary,
)

CATALOG_DIR = ROOT / "strategies" / "catalog"
# Outputs live outside the repo (outputs/ is a symlink); QRE_OUTPUT_DIR overrides.
OUTPUT_ROOT = Path(os.environ.get("QRE_OUTPUT_DIR", ROOT / "outputs"))
DEFAULT_OUTPUT = OUTPUT_ROOT / "backtests"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch backtest runner for strategy catalog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--category", help="Limit to one category directory")
    parser.add_argument("--strategies", nargs="*", help="Specific strategy IDs to run")
    parser.add_argument("--mode", choices=["smoke", "quick", "full"], default="smoke",
                        help="Date range preset (default: smoke)")
    parser.add_argument("--start", help="Override start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Override end date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Output base directory (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--backtest-mode", choices=["batch", "shared"], default="batch",
                        help="Backtest engine mode (default: batch)")
    parser.add_argument("--initial-cash", type=float, default=1_000_000,
                        help="Initial cash per symbol batch (default: 1,000,000)")
    parser.add_argument("--jobs", type=int, default=1,
                        help="Parallel worker processes (default: 1 = serial)")
    parser.add_argument("--compact", action="store_true",
                        help="Compact output: strategy-level aggregates only, no per-symbol trees")
    parser.add_argument("--workbook", action="store_true",
                        help="With --compact, also emit the full-market report bundle "
                             "(backtest_report.xlsx + HTML + charts) without per-symbol trees")
    parser.add_argument("--engine-impl", choices=["simulator", "vectorized"], default="vectorized",
                        help="Backtest engine implementation (default: vectorized; "
                             "metric-identical to simulator, ~40x faster)")
    parser.add_argument("--position-sizing", choices=["full_compound", "fixed_cash"],
                        default="full_compound",
                        help="Position sizing model (fixed_cash requires --engine-impl vectorized)")
    parser.add_argument("--metadata-columns", nargs="*",
                        help="Embed metadata columns (e.g. board industry_group market_cap_bucket liquidity_bucket) in summary.csv")
    parser.add_argument("--universe-filter", action="store_true",
                        help="Apply the strategy spec's universe rules (exclude_st/exclude_suspended/"
                             "exclude_risk_warning/min_listing_days/min_amount) before the engine")
    parser.add_argument("--commission-rate", type=float, help="Override market profile commission rate")
    parser.add_argument("--min-commission", type=float, help="Override market profile minimum commission")
    parser.add_argument("--stamp-tax", type=float, help="Override market profile sell stamp tax rate")
    parser.add_argument("--transfer-fee", type=float, help="Override market profile transfer fee rate")
    parser.add_argument("--slippage-buy", type=float, help="Override market profile buy slippage rate")
    parser.add_argument("--slippage-sell", type=float, help="Override market profile sell slippage rate")
    parser.add_argument("--apply-stops", action="store_true",
                        help="Honor stop_loss_pct/take_profit_pct from the strategy risk section")
    parser.add_argument("--stop-loss-pct", type=float,
                        help="Override spec stop_loss_pct (requires --apply-stops)")
    parser.add_argument("--take-profit-pct", type=float,
                        help="Override spec take_profit_pct (requires --apply-stops)")
    parser.add_argument("--trailing-stop-pct", type=float,
                        help="Override spec trailing_stop_pct (requires --apply-stops)")
    parser.add_argument("--symbol-chunk-size", type=int,
                        help="Process symbols in chunks of N (memory-safe for long windows)")
    parser.add_argument("--benchmark-table",
                        help="Benchmark table (e.g. reference.index_daily); requires --benchmark-code")
    parser.add_argument("--benchmark-code",
                        help="Benchmark ts_code (e.g. 000300.SH); requires --benchmark-table")
    parser.add_argument("--benchmark-value-column", default="close",
                        help="Benchmark value column (default: close)")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="Skip preflight stage (useful if DB factors are known good)")
    parser.add_argument("--skip-eval", action="store_true",
                        help="Skip evaluation stage (backtest only)")
    parser.add_argument("--min-factor-coverage", type=float, default=0.5,
                        help="Min factor coverage for preflight (default: 0.5)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip strategies that already have completed results")
    parser.add_argument("--max-strategies", type=int,
                        help="Limit number of strategies to run")
    parser.add_argument("--codes", nargs="*",
                        help="Limit to specific ts_codes (e.g. 000001.SZ 600000.SH)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List strategies without running")
    args = parser.parse_args()

    if not CATALOG_DIR.is_dir():
        print(f"Catalog not found: {CATALOG_DIR}", file=sys.stderr)
        print("Run: uv run python scripts/generate_strategy_yamls.py", file=sys.stderr)
        return 1

    # Discover strategies
    try:
        yaml_paths = discover_strategies(CATALOG_DIR, args.category, args.strategies)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.strategies:
        found = {p.stem for p in yaml_paths}
        for sid in args.strategies:
            if sid not in found:
                print(f"Warning: strategy '{sid}' not found in catalog", file=sys.stderr)
    if not yaml_paths:
        print("No strategy YAMLs found.")
        return 1

    # Resolve date range
    if args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
        mode_label = "custom"
    else:
        mc = MODE_CONFIGS[args.mode]
        start_date = date.fromisoformat(mc["start"])
        end_date = date.fromisoformat(mc["end"])
        mode_label = mc["label"]

    if (args.benchmark_table is None) != (args.benchmark_code is None):
        print("ERROR: --benchmark-table and --benchmark-code must be provided together", file=sys.stderr)
        return 1

    # Set up output
    batch_id = new_batch_id()
    output_base = args.output_dir / batch_id

    # Resume: skip completed
    if args.resume:
        completed = completed_strategies(args.output_dir)
        yaml_paths = [p for p in yaml_paths if p.stem not in completed]
        print(f"Resume mode: {len(completed)} already completed, {len(yaml_paths)} remaining")

    # Max strategies limit
    if args.max_strategies and len(yaml_paths) > args.max_strategies:
        yaml_paths = yaml_paths[: args.max_strategies]
        print(f"Limited to {args.max_strategies} strategies")

    print(f"\n{'='*70}")
    print("Batch Backtest Runner")
    print(f"  Strategies: {len(yaml_paths)}")
    print(f"  Date range: {start_date} to {end_date} ({mode_label})")
    print(f"  Output:     {output_base}")
    print(f"  Mode:       {args.backtest_mode}")
    print(f"  Jobs:       {args.jobs}")
    print(f"  Compact:    {'yes' if args.compact else 'no'}")
    print(f"  Preflight:  {'skip' if args.skip_preflight else 'enabled'}")
    print(f"{'='*70}\n")

    if args.dry_run:
        for yp in yaml_paths:
            print(f"  {yp.relative_to(CATALOG_DIR)}")
        return 0

    profile_overrides = {
        key: value
        for key, value in (
            ("commission_rate", args.commission_rate),
            ("min_commission", args.min_commission),
            ("stamp_tax_sell", args.stamp_tax),
            ("transfer_fee_rate", args.transfer_fee),
            ("slippage_buy_rate", args.slippage_buy),
            ("slippage_sell_rate", args.slippage_sell),
        )
        if value is not None
    }

    config = BatchRunConfig(
        output_base=output_base,
        start=start_date,
        end=end_date,
        skip_preflight=args.skip_preflight,
        skip_eval=args.skip_eval,
        backtest_mode=args.backtest_mode,
        initial_cash=args.initial_cash,
        min_factor_coverage=args.min_factor_coverage,
        codes=args.codes,
        compact=args.compact,
        include_full_market=args.workbook,
        catalog_dir=CATALOG_DIR,
        engine_impl=args.engine_impl,
        position_sizing=args.position_sizing,
        metadata_columns=args.metadata_columns,
        profile_overrides=profile_overrides or None,
        universe_filter=args.universe_filter,
        apply_stops=args.apply_stops,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        trailing_stop_pct=args.trailing_stop_pct,
        symbol_chunk_size=args.symbol_chunk_size,
        benchmark_table=args.benchmark_table,
        benchmark_code=args.benchmark_code,
        benchmark_value_column=args.benchmark_value_column,
    )

    results = execute_batch(yaml_paths, config, jobs=max(1, args.jobs))

    counts = summarize_results(results)
    summary = BatchSummary(
        batch_id=batch_id,
        generated_at=utc_now_iso(),
        mode=args.mode,
        date_range={"start": str(start_date), "end": str(end_date)},
        config={
            "backtest_mode": args.backtest_mode,
            "initial_cash": args.initial_cash,
            "skip_preflight": args.skip_preflight,
            "skip_eval": args.skip_eval,
            "min_factor_coverage": args.min_factor_coverage,
            "jobs": max(1, args.jobs),
            "compact": args.compact,
            "workbook": args.workbook,
            "engine_impl": args.engine_impl,
            "position_sizing": args.position_sizing,
            "universe_filter": args.universe_filter,
            "profile_overrides": profile_overrides or None,
            "apply_stops": args.apply_stops,
            "stop_loss_pct": args.stop_loss_pct,
            "take_profit_pct": args.take_profit_pct,
            "trailing_stop_pct": args.trailing_stop_pct,
            "symbol_chunk_size": args.symbol_chunk_size,
            "benchmark_table": args.benchmark_table,
            "benchmark_code": args.benchmark_code,
            "benchmark_value_column": args.benchmark_value_column,
        },
        results=results,
        summary=counts,
    )

    summary_path = write_batch_summary(summary, output_base)

    # Auto-queue shelved strategies' missing-factor requests (upstream handoff)
    shelved = [r for r in results if r.status == "missing_factors"]
    if shelved:
        from quant_research_engine.strategies.factor_request_queue import (
            load_queue,
            save_queue,
            upsert_requests,
        )

        queue_path = ROOT / "outputs" / "handoff" / "missing_factor_requests.json"
        entries = load_queue(queue_path)
        added = upsert_requests(
            entries, [req for r in shelved for req in r.missing_requests]
        )
        save_queue(queue_path, entries)
        print(f"Missing-factor queue: +{added} new request(s), "
              f"{len(shelved)} strateg(y/ies) shelved → {queue_path}")

    # Final report
    print(f"\n{'='*70}")
    print(f"Batch Complete: {batch_id}")
    print(f"  Total:   {counts['total']}")
    print(f"  OK:      {counts['ok']}")
    print(f"  Failed:  {counts['preflight_failed']} preflight, {counts['backtest_failed']} backtest, "
          f"{counts['error']} error")
    print(f"  Skipped: {counts['skipped']}")
    print(f"  Shelved: {counts.get('missing_factors', 0)} (missing factors)")
    print(f"  Summary: {summary_path}")
    print(f"{'='*70}")

    failures = counts["total"] - counts["ok"] - counts["skipped"] - counts.get("missing_factors", 0)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
