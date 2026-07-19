#!/usr/bin/env python3
"""Continuous strategy refresh: detect new data and re-run the catalog.

Usage:
  uv run python scripts/refresh_batch.py --check-only          # watermark vs state, no run
  uv run python scripts/refresh_batch.py                       # refresh if new data
  uv run python scripts/refresh_batch.py --force               # refresh regardless
  uv run python scripts/refresh_batch.py --codes 000001.SZ 600000.SH   # small-sample

State lives at outputs/refresh/state.json; batches at outputs/backtests/refresh/<id>/;
delta reports at outputs/refresh/delta/<timestamp>/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.orchestration.batch_runner import (
    BatchRunConfig,
    BatchSummary,
    discover_strategies,
    execute_batch,
    new_batch_id,
    summarize_results,
    utc_now_iso,
    write_batch_summary,
)
from quant_research_engine.orchestration.refresh import (
    compute_delta,
    compute_window,
    data_watermark,
    load_state,
    needs_refresh,
    save_state,
    write_delta_report,
    RefreshState,
)

CATALOG_DIR = ROOT / "strategies" / "catalog"
DEFAULT_BATCH_ROOT = ROOT / "outputs" / "backtests" / "refresh"
DEFAULT_STATE_FILE = ROOT / "outputs" / "refresh" / "state.json"
DEFAULT_DELTA_ROOT = ROOT / "outputs" / "refresh" / "delta"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continuous strategy refresh (watermark detection + idempotent re-run + delta report)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check-only", action="store_true", help="Report watermark vs state; do not run")
    parser.add_argument("--force", action="store_true", help="Refresh even when the watermark is unchanged")
    parser.add_argument("--window-years", type=int, default=2, help="Rolling window length in years (default: 2)")
    parser.add_argument("--jobs", type=int, default=4, help="Parallel workers (default: 4)")
    parser.add_argument("--codes", nargs="*", help="Limit symbols (small-sample/testing)")
    parser.add_argument("--with-eval", action="store_true", help="Also run the eval stage (slower)")
    parser.add_argument("--apply-stops", action="store_true", help="Honor spec stop_loss/take_profit")
    parser.add_argument("--universe-filter", action="store_true", help="Apply spec universe rules")
    parser.add_argument("--category", help="Limit to one catalog category")
    parser.add_argument("--strategies", nargs="*", help="Limit to specific strategy IDs")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_BATCH_ROOT)
    args = parser.parse_args()

    from quant_research_engine.data.postgres import PostgresDataStore
    from quant_research_engine.data.settings import DatabaseSettings

    store = PostgresDataStore(DatabaseSettings.from_env())
    data_date = data_watermark(store)
    close = getattr(store, "close", None)
    if data_date is None:
        print("ERROR: no data watermark (empty market table?)", file=sys.stderr)
        return 1

    state = load_state(args.state_file)
    print(f"data watermark: {data_date}")
    print(f"state: {state.last_data_date if state else '(none — first run)'}")

    if args.check_only:
        refresh_needed = needs_refresh(data_date, state)
        print(f"refresh needed: {refresh_needed}")
        return 0

    if not args.force and not needs_refresh(data_date, state):
        print("No new data since last refresh — nothing to do.")
        return 0

    start, end = compute_window(data_date, args.window_years)
    yaml_paths = discover_strategies(CATALOG_DIR, args.category, args.strategies)
    batch_id = new_batch_id()
    output_base = args.output_root / batch_id

    print(f"window: {start} → {end} ({args.window_years}y)")
    print(f"strategies: {len(yaml_paths)}; jobs: {args.jobs}; output: {output_base}")

    config = BatchRunConfig(
        output_base=output_base,
        start=start,
        end=end,
        skip_preflight=True,
        skip_eval=not args.with_eval,
        compact=True,
        catalog_dir=CATALOG_DIR,
        engine_impl="vectorized",
        codes=args.codes,
        apply_stops=args.apply_stops,
        universe_filter=args.universe_filter,
    )

    results = execute_batch(yaml_paths, config, jobs=max(1, args.jobs))
    counts = summarize_results(results)
    summary = BatchSummary(
        batch_id=batch_id,
        generated_at=utc_now_iso(),
        mode="refresh",
        date_range={"start": str(start), "end": str(end)},
        config={
            "engine_impl": "vectorized",
            "compact": True,
            "jobs": max(1, args.jobs),
            "with_eval": args.with_eval,
            "apply_stops": args.apply_stops,
            "universe_filter": args.universe_filter,
            "window_years": args.window_years,
        },
        results=results,
        summary=counts,
    )
    summary_path = write_batch_summary(summary, output_base)

    previous_batch_dir = Path(state.last_batch_dir) if state and state.last_batch_dir else None
    delta_rows = compute_delta(previous_batch_dir, output_base)
    delta_dir = DEFAULT_DELTA_ROOT / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{batch_id}"
    delta_paths = write_delta_report(
        delta_dir,
        data_date=data_date,
        window=(start, end),
        previous_batch_dir=previous_batch_dir,
        new_batch_dir=output_base,
        delta_rows=delta_rows,
    )

    save_state(
        args.state_file,
        RefreshState(
            last_data_date=str(data_date),
            last_run_at=utc_now_iso(),
            last_batch_dir=str(output_base),
            window_years=args.window_years,
            codes=args.codes,
            strategy_count=len(results),
            ok_count=counts["ok"],
            config=summary.config,
        ),
    )

    print(f"\nRefresh complete: {counts['ok']} ok / {counts['total']} total")
    print(f"  batch: {summary_path}")
    print(f"  delta: {delta_paths['delta_report_md']}")
    print(f"  state: {args.state_file}")
    if callable(close):
        close()
    return 0 if counts["total"] - counts["ok"] - counts["skipped"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
