#!/usr/bin/env python3
"""Strategy-fit report: significant-winner analysis over a completed batch.

Reads batch artifacts only (batch_summary.json + per-strategy summary.csv)
plus one read-only metadata snapshot query. No backtest execution.

Usage:
  uv run python scripts/strategy_fit_report.py --batch-dir outputs/backtests/quick_batch_106/f365c8a07b33
  uv run python scripts/strategy_fit_report.py --batch-dir <dir> --pool-tier 0.001 --min-trades 5
  uv run python scripts/strategy_fit_report.py --batch-dir <dir> --metadata-as-of 2024-12-31
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.analysis.strategy_fit import (
    TIER_ALPHAS,
    FitConfig,
    analyze_batch,
    load_batch,
    write_fit_outputs,
)

DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "strategy_fit"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strategy-fit report: significant-winner stock pools, meta-test tiers, class enrichment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--batch-dir", type=Path, required=True,
                        help="Completed batch directory containing batch_summary.json")
    parser.add_argument("--output-dir", type=Path,
                        help="Output directory (default: outputs/strategy_fit/<batch_id>)")
    parser.add_argument("--pool-tier", type=float, default=0.01,
                        help="Binomial p threshold for the stock pool (default: 0.01 = 99%% tier)")
    parser.add_argument("--tiers", type=str, default=",".join(str(a) for a in TIER_ALPHAS),
                        help="Comma-separated tier alphas (default: 0.1,0.01,0.001)")
    parser.add_argument("--min-trades", type=int, default=5,
                        help="Minimum trade count for a symbol to be eligible (default: 5)")
    parser.add_argument("--min-class-size", type=int, default=30,
                        help="Minimum universe size for a class to be reportable (default: 30)")
    parser.add_argument("--metadata-as-of", type=str,
                        help="Metadata snapshot date YYYY-MM-DD (default: batch end date)")
    parser.add_argument("--no-metadata", action="store_true",
                        help="Skip DB metadata (all classes become 'unknown'; for offline checks)")
    args = parser.parse_args()

    tiers = tuple(sorted(float(t) for t in args.tiers.split(",")))
    if args.pool_tier not in tiers:
        print(f"Warning: pool_tier {args.pool_tier} not in tiers {tiers}", file=sys.stderr)
    config = FitConfig(
        tiers=tiers,
        pool_tier=args.pool_tier,
        min_trades=args.min_trades,
        min_class_size=args.min_class_size,
    )

    # Resolve metadata snapshot date (default: batch end date)
    import json as _json
    batch_payload = _json.loads((args.batch_dir / "batch_summary.json").read_text(encoding="utf-8"))
    batch_end = (batch_payload.get("date_range") or {}).get("end")
    metadata_as_of = date.fromisoformat(args.metadata_as_of) if args.metadata_as_of else (
        date.fromisoformat(batch_end) if batch_end else None
    )

    if args.no_metadata:
        import pandas as pd
        metadata = pd.DataFrame(columns=["ts_code"])
    else:
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.data.settings import DatabaseSettings
        from quant_research_engine.data.tushare_security import derive_board

        symbols = sorted({
            symbol
            for data in load_batch(args.batch_dir)[0]
            for symbol in data.frame["symbol"].astype(str)
        })
        store = PostgresDataStore(DatabaseSettings.from_env())
        # stock_basic is not populated upstream yet; compose metadata from
        # available sources: daily_basic snapshot (cap/liquidity buckets) +
        # board derived from ts_code. industry_group stays 'unknown'.
        metadata = store._load_reference_daily_basic_snapshot(symbols, as_of=metadata_as_of)
        close = getattr(store, "close", None)
        if callable(close):
            close()
        import pandas as pd
        if metadata.empty:
            metadata = pd.DataFrame({"ts_code": symbols})
        metadata["board"] = metadata["ts_code"].map(derive_board)
        if "total_mv" in metadata.columns:
            metadata["market_cap_bucket"] = PostgresDataStore._compute_market_cap_bucket(metadata["total_mv"])
        if "turnover_rate_f" in metadata.columns:
            metadata["liquidity_bucket"] = PostgresDataStore._compute_liquidity_bucket(metadata["turnover_rate_f"])
        if "industry_group" not in metadata.columns:
            metadata["industry_group"] = "unknown"
        print(f"metadata: {len(metadata)} symbols (as_of={metadata_as_of}, source=daily_basic+derive_board)")

    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / args.batch_dir.name)

    summary_df, stocks_df, classes_df, skipped = analyze_batch(args.batch_dir, metadata, config)
    paths = write_fit_outputs(
        output_dir,
        summary_df,
        stocks_df,
        classes_df,
        skipped,
        batch_dir=args.batch_dir,
        config=config,
    )

    edge_count = int(summary_df["class_edge"].sum()) if not summary_df.empty and "class_edge" in summary_df.columns else 0
    meta_counts = summary_df["meta_tier"].value_counts().to_dict() if not summary_df.empty else {}
    print(f"\nStrategy Fit Report")
    print(f"  strategies: {len(summary_df)} analyzed, {len(skipped)} skipped")
    print(f"  meta tiers: {meta_counts}")
    print(f"  class_edge strategies: {edge_count}")
    print(f"  pool stocks (tier>={config.pool_tier}): {int(stocks_df['in_pool'].sum()) if not stocks_df.empty else 0}")
    print(f"  output: {output_dir}")
    print(f"  manifest: {paths['report_manifest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
