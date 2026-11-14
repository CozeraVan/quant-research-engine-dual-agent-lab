#!/usr/bin/env python3
"""Analyze a standard backtest-batch result with M10.1/M10.4 (no re-backtest).

Usage:
  .venv-ml/bin/python scripts/strategy_fit_batch.py --batch-dir <dir>
  .venv-ml/bin/python scripts/strategy_fit_batch.py --batch-dir <dir> --no-metadata
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.analysis.ml_cluster import (  # noqa: E402
    MlClusterConfig,
    analyze_fit_stocks,
    write_ml_outputs,
)
from quant_research_engine.analysis.strategy_fit import (  # noqa: E402
    DIMENSIONS,
    FitConfig,
    StrategyBatchData,
    analyze_strategy,
    benjamini_hochberg,
    write_fit_outputs,
)


def analyze_standard_batch(
    batch_dir: Path,
    output_dir: Path,
    metadata: pd.DataFrame,
    fit_config: FitConfig,
    ml_config: MlClusterConfig,
) -> dict:
    batch_dir = Path(batch_dir)
    summary_path = batch_dir / "summary.csv"
    if not summary_path.is_file():
        raise FileNotFoundError(f"standard batch summary.csv not found: {summary_path}")
    frame = pd.read_csv(summary_path)
    # 分类元数据只能来自只读 snapshot，避免 summary 同名列在 merge 后变成 board_x/y。
    frame = frame.drop(columns=[column for column in DIMENSIONS if column in frame.columns])
    monthly_path = batch_dir / "symbol_month_returns.csv"
    monthly = pd.read_csv(monthly_path) if monthly_path.is_file() else None
    data = StrategyBatchData(
        strategy_id=batch_dir.name,
        category="standard_batch",
        frame=frame,
        monthly=monthly,
    )
    fit = analyze_strategy(data, metadata, fit_config)
    q_values = benjamini_hochberg([row["p_value"] for row in fit.class_rows])
    for row, q_value in zip(fit.class_rows, q_values):
        row["q_value"] = q_value
    summary_row = fit.summary_row
    best_key = (summary_row["strategy_id"], summary_row.get("best_dimension"), summary_row.get("best_class"))
    best_q = {
        (row["strategy_id"], row["dimension"], row["class_value"]): row["q_value"]
        for row in fit.class_rows
    }.get(best_key)
    summary_row["best_class_q"] = best_q
    summary_row["class_edge"] = bool(
        summary_row["meta_tier"]
        and summary_row.get("best_class_pool_mean_excess") is not None
        and summary_row.get("market_mean_excess") is not None
        and best_q is not None
        and best_q <= 0.05
        and (summary_row["best_class_pool_mean_excess"] - summary_row["market_mean_excess"])
        >= fit_config.class_edge_min_pp
    )
    summary_df = pd.DataFrame([summary_row])
    stocks_df = pd.DataFrame(fit.stock_rows)
    classes_df = pd.DataFrame(fit.class_rows)
    fit_paths = write_fit_outputs(
        output_dir / "fit",
        summary_df,
        stocks_df,
        classes_df,
        [],
        batch_dir=batch_dir,
        config=fit_config,
    )
    if stocks_df.empty:
        ml_stocks, ml_clusters = stocks_df.copy(), pd.DataFrame()
        ml_status = [{
            "strategy_id": summary_row["strategy_id"],
            "category": summary_row["category"],
            "status": "insufficient",
            "reason": "no stocks pass the loosest significance tier and return gates",
            "n_stocks": 0,
            "n_clusters": 0,
            "n_noise": 0,
            "imputed_features": {},
            "constant_features": [],
        }]
    else:
        ml_stocks, ml_clusters, ml_status = analyze_fit_stocks(stocks_df, metadata, ml_config)
    ml_paths = write_ml_outputs(
        output_dir / "ml",
        ml_stocks,
        ml_clusters,
        ml_status,
        fit_dir=output_dir / "fit",
        config=ml_config,
        metadata=metadata,
    )
    return {
        "fit_summary": fit.summary_row,
        "ml_status": ml_status,
        "fit_manifest": str(fit_paths["report_manifest"]),
        "ml_manifest": str(ml_paths["ml_cluster_manifest"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--pool-tier", type=float, default=0.01)
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--min-class-size", type=int, default=30)
    parser.add_argument("--eps", type=float, default=1.0)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--min-cluster-size", type=int, default=3)
    parser.add_argument("--metadata-as-of")
    parser.add_argument("--metadata-csv", type=Path, help="Offline metadata snapshot")
    parser.add_argument("--no-metadata", action="store_true")
    parser.add_argument("--force", action="store_true", help="Reanalyze even when outputs are current")
    args = parser.parse_args()
    output_dir = args.output_dir or ROOT / "outputs" / "strategy_fit" / args.batch_dir.name
    manifest_path = output_dir / "ml" / "ml_cluster_manifest.json"
    if not args.force and manifest_path.is_file() and (
        (args.batch_dir / "summary.csv").stat().st_mtime <= manifest_path.stat().st_mtime
    ):
        print({"status": "unchanged", "manifest": str(manifest_path)})
        return 0
    fit_config = FitConfig(
        pool_tier=args.pool_tier,
        min_trades=args.min_trades,
        min_class_size=args.min_class_size,
    )
    ml_config = MlClusterConfig(
        eps=args.eps,
        min_samples=args.min_samples,
        min_cluster_size=args.min_cluster_size,
    )
    if args.no_metadata:
        metadata = pd.DataFrame(columns=["ts_code"])
    elif args.metadata_csv:
        metadata = pd.read_csv(args.metadata_csv)
    else:
        from quant_research_engine.data.metadata_compose import compose_symbol_metadata
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.data.settings import DatabaseSettings

        frame = pd.read_csv(args.batch_dir / "summary.csv")
        symbols = sorted(frame["symbol"].astype(str).unique())
        as_of = date.fromisoformat(args.metadata_as_of) if args.metadata_as_of else None
        store = PostgresDataStore(DatabaseSettings.from_env())
        metadata = compose_symbol_metadata(store, symbols, as_of=as_of)
        close = getattr(store, "close", None)
        if callable(close):
            close()
    result = analyze_standard_batch(args.batch_dir, output_dir, metadata, fit_config, ml_config)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
