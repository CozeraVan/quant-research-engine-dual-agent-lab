#!/usr/bin/env python3
"""Batch backtest runner for all strategy catalog YAMLs.

Usage:
  uv run python scripts/batch_backtest_runner.py                    # run all
  uv run python scripts/batch_backtest_runner.py --category mean_reversion
  uv run python scripts/batch_backtest_runner.py --strategies tf01a rsi2
  uv run python scripts/batch_backtest_runner.py --start 2020-01-01 --end 2024-12-31
  uv run python scripts/batch_backtest_runner.py --mode smoke       # 2-month smoke
  uv run python scripts/batch_backtest_runner.py --mode full        # full history
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
      backtest/...                  — backtest artifacts
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "strategies" / "catalog"
DEFAULT_OUTPUT = ROOT / "outputs" / "backtests"

MODE_CONFIGS = {
    "smoke": {"start": "2024-01-01", "end": "2024-03-01", "label": "Smoke (2 months)"},
    "quick": {"start": "2024-01-01", "end": "2024-12-31", "label": "Quick (1 year)"},
    "full": {"start": "2015-01-01", "end": "2025-12-31", "label": "Full (2015-2025)"},
}


@dataclass
class BatchRunResult:
    strategy_id: str
    category: str
    research_run_id: str
    status: str  # ok | preflight_failed | eval_failed | backtest_failed | error | skipped
    preflight_status: str = ""
    eval_status: str = ""
    backtest_status: str = ""
    output_dir: str = ""
    error_message: str = ""
    duration_s: float = 0.0


@dataclass
class BatchSummary:
    batch_id: str
    generated_at: str
    mode: str
    date_range: dict[str, str]
    config: dict[str, Any]
    results: list[BatchRunResult] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


def discover_strategies(
    catalog_dir: Path,
    category: str | None = None,
    strategy_ids: list[str] | None = None,
) -> list[Path]:
    """Find strategy YAML files, optionally filtered."""
    if strategy_ids:
        paths = []
        for sid in strategy_ids:
            matches = list(catalog_dir.rglob(f"{sid}.yaml"))
            if matches:
                paths.extend(matches)
            else:
                print(f"Warning: strategy '{sid}' not found in catalog", file=sys.stderr)
        return sorted(set(paths))

    if category:
        target = catalog_dir / category
        if not target.is_dir():
            print(f"Category not found: {category}", file=sys.stderr)
            sys.exit(1)
        return sorted(target.glob("*.yaml"))

    return sorted(catalog_dir.rglob("*.yaml"))


def get_completed_strategies(output_base: Path) -> set[str]:
    """Find strategy IDs that already have complete results."""
    completed = set()
    if not output_base.is_dir():
        return completed
    for run_dir in output_base.iterdir():
        if not run_dir.is_dir():
            continue
        manifest = run_dir / "research_run_manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                stages = data.get("stages", {})
                if stages.get("backtest") == "ok":
                    # Extract strategy ID from strategy_path
                    sp = data.get("strategy_path", "")
                    sid = Path(sp).stem
                    completed.add(sid)
            except (json.JSONDecodeError, KeyError):
                pass
    return completed


def run_single_strategy(
    yaml_path: Path,
    output_base: Path,
    start: date,
    end: date,
    *,
    skip_preflight: bool = False,
    skip_eval: bool = False,
    backtest_mode: str = "batch",
    initial_cash: float = 1_000_000,
    min_factor_coverage: float = 0.5,
    codes: list[str] | None = None,
) -> BatchRunResult:
    """Run a single strategy through the research-run pipeline."""
    from quant_research_engine.orchestration.research_run import (
        ResearchRunRequest,
        run_research_run,
    )

    rel = yaml_path.relative_to(CATALOG_DIR)
    category = rel.parts[0] if len(rel.parts) > 1 else "root"
    strategy_id = yaml_path.stem

    t0 = time.perf_counter()
    output_dir = output_base / strategy_id

    result = BatchRunResult(
        strategy_id=strategy_id,
        category=category,
        research_run_id="",
        status="error",
        output_dir=str(output_dir),
    )

    try:
        req = ResearchRunRequest(
            strategy_path=yaml_path,
            start=start,
            end=end,
            output_dir=output_dir,
            backtest_mode=backtest_mode if backtest_mode in ("batch", "shared") else "batch",
            skip_preflight=skip_preflight,
            skip_eval=skip_eval,
            initial_cash=initial_cash,
            min_factor_coverage=min_factor_coverage,
            codes=codes,
        )

        run_result = run_research_run(req)
        result.research_run_id = run_result.run_id
        result.preflight_status = run_result.preflight_status
        result.eval_status = run_result.eval_status
        result.backtest_status = run_result.backtest_status

        if run_result.preflight_status == "error":
            result.status = "preflight_failed"
        elif run_result.eval_status == "error":
            result.status = "eval_failed"
        elif run_result.backtest_status == "error":
            result.status = "backtest_failed"
        else:
            result.status = "ok"

        if run_result.error_message:
            result.error_message = run_result.error_message

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)

    result.duration_s = time.perf_counter() - t0
    return result


def write_batch_summary(summary: BatchSummary, output_base: Path) -> Path:
    """Write the master batch_summary.json."""
    output_base.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "batch_id": summary.batch_id,
        "generated_at": summary.generated_at,
        "mode": summary.mode,
        "date_range": summary.date_range,
        "config": summary.config,
        "summary": summary.summary,
        "results": [
            {
                "strategy_id": r.strategy_id,
                "category": r.category,
                "research_run_id": r.research_run_id,
                "status": r.status,
                "preflight_status": r.preflight_status,
                "eval_status": r.eval_status,
                "backtest_status": r.backtest_status,
                "output_dir": r.output_dir,
                **({"error_message": r.error_message} if r.error_message else {}),
                "duration_s": round(r.duration_s, 1),
            }
            for r in summary.results
        ],
    }

    path = output_base / "batch_summary.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def print_progress(i: int, total: int, result: BatchRunResult) -> None:
    """Print a one-line progress update."""
    status_icon = {"ok": "+", "preflight_failed": "P", "eval_failed": "E",
                    "backtest_failed": "B", "error": "X", "skipped": "S"}
    icon = status_icon.get(result.status, "?")
    dur = f"{result.duration_s:.0f}s"
    print(f"  [{i}/{total}] {icon} {result.strategy_id:45s} {result.status:20s} {dur}")


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
    yaml_paths = discover_strategies(CATALOG_DIR, args.category, args.strategies)
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
    batch_id = uuid.uuid4().hex[:12]
    output_base = args.output_dir / batch_id

    # Resume: skip completed
    if args.resume:
        completed = get_completed_strategies(args.output_dir)
        yaml_paths = [p for p in yaml_paths if p.stem not in completed]
        print(f"Resume mode: {len(completed)} already completed, {len(yaml_paths)} remaining")

    # Max strategies limit
    if args.max_strategies and len(yaml_paths) > args.max_strategies:
        yaml_paths = yaml_paths[:args.max_strategies]
        print(f"Limited to {args.max_strategies} strategies")

    print(f"\n{'='*70}")
    print(f"Batch Backtest Runner")
    print(f"  Strategies: {len(yaml_paths)}")
    print(f"  Date range: {start_date} to {end_date} ({mode_label})")
    print(f"  Output:     {output_base}")
    print(f"  Mode:       {args.backtest_mode}")
    print(f"  Preflight:  {'skip' if args.skip_preflight else 'enabled'}")
    print(f"{'='*70}\n")

    if args.dry_run:
        for yp in yaml_paths:
            rel = yp.relative_to(CATALOG_DIR)
            print(f"  {rel}")
        return 0

    # Run all strategies
    results: list[BatchRunResult] = []
    skipped = 0
    errors = 0

    for i, yp in enumerate(yaml_paths):
        result = run_single_strategy(
            yp,
            output_base,
            start_date,
            end_date,
            skip_preflight=args.skip_preflight,
            skip_eval=args.skip_eval,
            backtest_mode=args.backtest_mode,
            initial_cash=args.initial_cash,
            min_factor_coverage=args.min_factor_coverage,
            codes=args.codes,
        )
        results.append(result)

        if result.status == "skipped":
            skipped += 1
        elif result.status != "ok":
            errors += 1

        print_progress(i + 1, len(yaml_paths), result)

    # Build summary
    ok_count = sum(1 for r in results if r.status == "ok")
    pf_fail = sum(1 for r in results if r.status == "preflight_failed")

    summary = BatchSummary(
        batch_id=batch_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=args.mode,
        date_range={"start": str(start_date), "end": str(end_date)},
        config={
            "backtest_mode": args.backtest_mode,
            "initial_cash": args.initial_cash,
            "skip_preflight": args.skip_preflight,
            "skip_eval": args.skip_eval,
            "min_factor_coverage": args.min_factor_coverage,
        },
        results=results,
        summary={
            "total": len(results),
            "ok": ok_count,
            "preflight_failed": pf_fail,
            "eval_failed": sum(1 for r in results if r.status == "eval_failed"),
            "backtest_failed": sum(1 for r in results if r.status == "backtest_failed"),
            "error": sum(1 for r in results if r.status == "error"),
            "skipped": skipped,
        },
    )

    summary_path = write_batch_summary(summary, output_base)

    # Final report
    print(f"\n{'='*70}")
    print(f"Batch Complete: {batch_id}")
    print(f"  Total:   {len(results)}")
    print(f"  OK:      {ok_count}")
    print(f"  Failed:  {pf_fail} preflight, {summary.summary['backtest_failed']} backtest, "
          f"{summary.summary['error']} error")
    print(f"  Skipped: {skipped}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*70}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
