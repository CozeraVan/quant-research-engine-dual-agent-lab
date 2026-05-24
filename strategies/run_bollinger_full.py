#!/usr/bin/env python3
"""Chunked full-market backtest runner for Bollinger Band Mean Reversion.

Processes symbols in small chunks with incremental disk persistence.
Produces:
  - outputs/bollinger_mean_reversion_full/batch/summary.csv (incremental)
  - outputs/bollinger_mean_reversion_full/batch/aggregate_summary.json (final)
  - outputs/bollinger_mean_reversion_full/batch/.progress (resume marker)
"""
from __future__ import annotations

import gc
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.strategies.spec import StrategySpec


CHUNK_SIZE = 100  # smaller chunks for memory safety
SPEC_PATH = Path("strategies/low_level/bollinger_mean_reversion.yaml")
OUTPUT_DIR = Path("outputs/bollinger_mean_reversion_full/batch")
START = "2010-01-04"
END = "2026-05-22"
INITIAL_CASH = 1_000_000
PROGRESS_FILE = OUTPUT_DIR / ".progress"


def get_all_symbols(settings: DatabaseSettings) -> list[str]:
    engine = create_engine(settings.market_db_url)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT DISTINCT ts_code FROM public.stock_daily "
                    "WHERE trade_date >= :start AND trade_date <= :end "
                    "ORDER BY ts_code"
                ),
                {"start": START, "end": END},
            )
            return [row[0] for row in result.fetchall()]
    finally:
        engine.dispose()


def save_incremental(chunk_idx: int, summary: pd.DataFrame) -> None:
    """Append summary rows to disk incrementally."""
    csv_path = OUTPUT_DIR / "summary.csv"
    header = not csv_path.exists()
    summary.to_csv(csv_path, mode="a", index=False, header=header)
    # Save progress
    PROGRESS_FILE.write_text(str(chunk_idx))


def write_aggregate_summary() -> None:
    """Generate aggregate_summary.json from the completed summary.csv."""
    summary_path = OUTPUT_DIR / "summary.csv"
    if not summary_path.exists():
        return
    df = pd.read_csv(summary_path)
    if df.empty:
        return

    returns = df["total_return"].dropna()
    n = len(df)
    traded = int((df["trade_count"] > 0).sum())
    total_trades = int(df["trade_count"].sum())
    total_cost = float(df["total_cost"].sum())
    mean_ret = float(returns.mean())
    median_ret = float(returns.median())
    pos_rate = float((returns > 0).mean())
    mean_equity = float(df["final_equity"].mean()) if "final_equity" in df.columns else None
    failed = int(df["failed_order_count"].sum()) if "failed_order_count" in df.columns else 0

    # Return distribution buckets
    bins = [float("-inf"), -0.50, -0.20, -0.10, 0, 0.10, 0.20, 0.50, float("inf")]
    labels = ["<-50%", "-50~-20%", "-20~-10%", "-10~0%", "0~10%", "10~20%", "20~50%", ">50%"]
    dist = []
    for i, label in enumerate(labels):
        lo, hi = bins[i], bins[i + 1]
        cnt = int(((returns > lo) & (returns <= hi)).sum()) if i < len(labels) - 1 else 0
        # Last bucket: >50%
        if i == len(labels) - 2:
            cnt = int((returns > lo).sum())
        dist.append({"label": label, "count": cnt})

    # Recompute last bucket
    dist[-1]["count"] = int((returns > 0.50).sum())

    # Best / worst symbols
    best = df.nlargest(10, "total_return")
    worst = df.nsmallest(5, "total_return")

    aggregate = {
        "strategy": "bollinger_mean_reversion",
        "start": START,
        "end": END,
        "total_symbols": n,
        "traded_symbols": traded,
        "total_trades": total_trades,
        "total_cost": total_cost,
        "mean_return": mean_ret,
        "median_return": median_ret,
        "positive_return_rate": pos_rate,
        "mean_final_equity": mean_equity,
        "failed_orders": failed,
        "return_distribution": dist,
        "best_symbols": [
            {"symbol": row["symbol"], "total_return": row["total_return"],
             "trade_count": int(row["trade_count"])}
            for _, row in best.iterrows()
        ],
        "worst_symbols": [
            {"symbol": row["symbol"], "total_return": row["total_return"],
             "trade_count": int(row["trade_count"])}
            for _, row in worst.iterrows()
        ],
    }
    agg_path = OUTPUT_DIR / "aggregate_summary.json"
    agg_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Aggregate summary: {agg_path}")


def load_progress() -> int:
    if PROGRESS_FILE.exists():
        return int(PROGRESS_FILE.read_text().strip())
    return 0


def main() -> int:
    settings = DatabaseSettings.from_env()
    print(f"DB URL: {settings.market_db_url}")

    store = PostgresDataStore(settings)
    store.ping()
    print("DB ping OK")

    spec = StrategySpec.from_yaml(SPEC_PATH)
    market_profile = AShareMarketProfile()

    all_symbols = get_all_symbols(settings)
    if not all_symbols:
        print("No symbols found", file=sys.stderr)
        return 1

    n_symbols = len(all_symbols)
    n_chunks = (n_symbols + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"Strategy: {spec.name}")
    print(f"Entry: {spec.signal_expression}")
    print(f"Exit: {spec.exit_signal_expression}")
    print(f"Total symbols: {n_symbols}, chunk size: {CHUNK_SIZE}, chunks: {n_chunks}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    start_chunk = load_progress()
    if start_chunk > 0:
        print(f"Resuming from chunk {start_chunk + 1} (already completed {start_chunk} chunks)")

    for chunk_idx in range(start_chunk, n_chunks):
        chunk_start = chunk_idx * CHUNK_SIZE
        chunk_end = min(chunk_start + CHUNK_SIZE, n_symbols)
        chunk_symbols = all_symbols[chunk_start:chunk_end]
        chunk_label = f"[{chunk_idx + 1}/{n_chunks}]"
        print(f"\n{chunk_label} Symbols {chunk_start}-{chunk_end - 1} ({len(chunk_symbols)} symbols)")

        try:
            frame = ResearchFrameAssembler(store).build(
                ts_codes=chunk_symbols,
                start=START,
                end=END,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                include_metadata=True,
            )
        except Exception as exc:
            print(f"  ERROR loading data: {exc}", file=sys.stderr)
            continue

        if frame is None or len(frame) == 0:
            print(f"  No data")
            save_incremental(chunk_idx + 1, pd.DataFrame())
            continue

        print(f"  Frame rows: {len(frame)}")

        try:
            result = BatchBacktestEngine(market_profile).run(
                frame,
                BatchBacktestRequest(
                    symbols=chunk_symbols,
                    initial_cash_per_symbol=INITIAL_CASH,
                    entry_signal=spec.signal_expression,
                    exit_signal=spec.exit_signal_expression,
                    holding_days=spec.holding_days,
                ),
            )
        except Exception as exc:
            print(f"  ERROR backtest: {exc}", file=sys.stderr)
            del frame
            gc.collect()
            continue

        n_traded = len(result.summary[result.summary["trade_count"] > 0])
        chunk_trades = int(result.summary["trade_count"].sum())
        chunk_cost = float(result.summary["total_cost"].sum())
        chunk_mean = float(result.summary["total_return"].mean())
        print(f"  Traded: {n_traded}/{len(chunk_symbols)}, trades: {chunk_trades}, cost: {chunk_cost:.2f}, mean_ret: {chunk_mean:.4f}")

        save_incremental(chunk_idx + 1, result.summary)

        del frame
        del result
        gc.collect()

    print("\nAll chunks complete.")
    write_aggregate_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
