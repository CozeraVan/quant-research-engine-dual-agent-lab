#!/usr/bin/env python3
"""M10.4 ML cluster & noise report over an existing M10.1 strategy-fit output.

Reads the per-stock rows that ``scripts/strategy_fit_report.py`` (M10.1)
already judged significant (binomial tiers 90%/99%/99.9% + excess-return
gate) and clusters them per strategy with DBSCAN, labeling outliers as
noise. Tier/gate semantics are inherited unchanged — no statistics are
recomputed and no backtest is executed.

Requires scikit-learn: run with the project's ``.venv-ml``. In the main
environment (no scikit-learn) the CLI degrades gracefully with a clear
message and exit code 2; all other QRE functionality is unaffected.

Usage:
  .venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir outputs/strategy_fit/f365c8a07b33
  .venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir <dir> --eps 1.5 --min-samples 4
  .venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir <dir> --metadata-csv meta.csv --pool-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "strategy_fit_ml"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="M10.4 ML cluster & noise report over an existing M10.1 strategy-fit output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--fit-dir", type=Path, required=True,
                        help="Existing M10.1 fit output directory (contains strategy_fit_stocks.csv)")
    parser.add_argument("--output-dir", type=Path,
                        help="Output directory (default: outputs/strategy_fit_ml/<fit_dir_name>)")
    parser.add_argument("--metadata-csv", type=Path,
                        help="Optional read-only metadata CSV keyed by ts_code/symbol; extra "
                             "numeric/categorical columns enrich the feature matrix")
    parser.add_argument("--eps", type=float, default=1.0,
                        help="DBSCAN eps on standardized features (default: 1.0)")
    parser.add_argument("--min-samples", type=int, default=5,
                        help="DBSCAN min_samples; strategies with fewer significant stocks are "
                             "reported as insufficient (default: 5)")
    parser.add_argument("--min-cluster-size", type=int, default=3,
                        help="Minimum members for a cluster to be reported (default: 3)")
    parser.add_argument("--random-state", type=int, default=42,
                        help="Random seed recorded in the manifest for the reproducibility contract (default: 42)")
    parser.add_argument("--pool-only", action="store_true",
                        help="Cluster only the in_pool stocks (binomial p <= pool tier) instead of all significant stocks")
    args = parser.parse_args()

    from quant_research_engine.analysis.ml_cluster import (
        MlClusterConfig,
        analyze_fit_stocks,
        load_fit_stocks,
        load_metadata_csv,
        ml_cluster_available,
        write_ml_outputs,
    )

    if not ml_cluster_available():
        print(
            "ERROR: scikit-learn is not installed in this environment. "
            "Run with the project's .venv-ml:\n"
            "  .venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir <dir>\n"
            "The main environment degrades gracefully; all non-ML functionality is unaffected.",
            file=sys.stderr,
        )
        return 2

    config = MlClusterConfig(
        eps=args.eps,
        min_samples=args.min_samples,
        min_cluster_size=args.min_cluster_size,
        random_state=args.random_state,
        pool_only=args.pool_only,
    )

    stocks = load_fit_stocks(args.fit_dir)
    metadata = load_metadata_csv(args.metadata_csv) if args.metadata_csv else None
    if metadata is not None:
        print(f"metadata: {len(metadata)} symbols from {args.metadata_csv}")

    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, metadata, config)
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / args.fit_dir.name)
    paths = write_ml_outputs(
        output_dir,
        stocks_df,
        clusters_df,
        status_rows,
        fit_dir=args.fit_dir,
        config=config,
        metadata=metadata,
    )

    status_counts: dict[str, int] = {}
    for row in status_rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    n_noise = int(stocks_df["is_noise"].sum()) if not stocks_df.empty and "is_noise" in stocks_df.columns else 0
    print("\nML Cluster & Noise Report (M10.4)")
    print(f"  strategies: {len(status_rows)} analyzed; statuses: {status_counts}")
    print(f"  significant stocks clustered: {len(stocks_df)}; noise: {n_noise}")
    print(f"  output: {output_dir}")
    print(f"  manifest: {paths['ml_cluster_manifest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
