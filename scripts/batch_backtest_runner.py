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
DEFAULT_OUTPUT = ROOT / "outputs" / "backtests"


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
        catalog_dir=CATALOG_DIR,
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
        },
        results=results,
        summary=counts,
    )

    summary_path = write_batch_summary(summary, output_base)

    # Final report
    print(f"\n{'='*70}")
    print(f"Batch Complete: {batch_id}")
    print(f"  Total:   {counts['total']}")
    print(f"  OK:      {counts['ok']}")
    print(f"  Failed:  {counts['preflight_failed']} preflight, {counts['backtest_failed']} backtest, "
          f"{counts['error']} error")
    print(f"  Skipped: {counts['skipped']}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*70}")

    failures = counts["total"] - counts["ok"] - counts["skipped"]
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
