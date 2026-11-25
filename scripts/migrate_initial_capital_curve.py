#!/usr/bin/env python3
"""Rebuild a batch run's equity curve on the reserved-initial-capital basis.

This is a report-only migration: it reads existing per-symbol artifacts and never
re-runs trading. Use --output-dir for smoke validation, then --apply after the
terminal return has been reconciled with strategy_performance.json.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine, text

from quant_research_engine.portfolio.benchmark import excess_return_vs_sse
from quant_research_engine.portfolio.full_market_report import (
    build_drawdown_curve,
    build_full_market_equity_curve,
)
from quant_research_engine.portfolio.risk import summarize_equity_curve


def rebuild(run_dir: Path, output_dir: Path) -> dict:
    artifacts = run_dir / "artifacts"
    # output_dir隔离的新任务多一层run_id；旧任务为平铺目录。
    if not (artifacts / "strategy_performance.json").exists() and (artifacts / run_dir.name).is_dir():
        artifacts = artifacts / run_dir.name
    results = {}
    request_path = run_dir / "request.json"
    request = json.loads(request_path.read_text()) if request_path.exists() else {}
    if request.get("mode") == "shared_cash":
        curve = pd.read_csv(artifacts / "equity_curve.csv")
        initial = float(curve["total_equity"].iloc[0])
        curve["daily_return"] = curve["total_equity"].pct_change(fill_method=None)
        curve["cumulative_return"] = curve["total_equity"] / initial - 1.0
    else:
        for symbol_dir in sorted(artifacts.iterdir()):
            if not symbol_dir.is_dir():
                continue
            equity_path = symbol_dir / "equity_curve.csv"
            summary_path = symbol_dir / "summary.json"
            if not summary_path.exists():
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            try:
                equity = pd.read_csv(equity_path) if equity_path.exists() and equity_path.stat().st_size else pd.DataFrame()
            except pd.errors.EmptyDataError:
                equity = pd.DataFrame()
            results[symbol_dir.name] = SimpleNamespace(equity_curve=equity, summary=summary)
        if not results:
            raise RuntimeError(f"no per-symbol artifacts in {artifacts}")
        curve = build_full_market_equity_curve(results)
    performance_path = artifacts / "strategy_performance.json"
    performance = json.loads(performance_path.read_text(encoding="utf-8"))
    expected = float(performance["strategy_total_return"])
    actual = float(curve["cumulative_return"].iloc[-1])
    if abs(actual - expected) > 1e-8:
        raise RuntimeError(f"terminal return mismatch: curve={actual}, performance={expected}, curve_equity={curve['total_equity'].iloc[-1]}, summary_equity={sum(float(r.summary['final_equity']) for r in results.values())}, summary_initial={sum(float(r.summary['initial_cash']) for r in results.values())}")

    dates = pd.to_datetime(curve["trade_date"]).dt.strftime("%Y-%m-%d")
    engine = create_engine(os.environ.get("QRE_MARKET_DB_URL", "postgresql+psycopg:///tushare_data"))
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT trade_date, close FROM reference.index_daily "
                 "WHERE ts_code='000001.SH' AND trade_date BETWEEN :start AND :end ORDER BY trade_date"),
            {"start": dates.iloc[0], "end": dates.iloc[-1]},
        ).fetchall()
    if not rows:
        benchmark_return = None
    else:
        benchmark_return = float(rows[-1][1]) / float(rows[0][1]) - 1.0
    risk = summarize_equity_curve(curve)
    performance.update({
        "benchmark_code": "000001.SH",
        "benchmark_name": "上证指数",
        "benchmark_return": benchmark_return,
        "excess_return_vs_benchmark": excess_return_vs_sse(actual, benchmark_return),
        "max_drawdown": risk.get("max_drawdown"),
        "max_drawdown_duration_days": risk.get("max_drawdown_duration_days"),
        "recovery_factor": risk.get("return_drawdown_ratio"),
        "sharpe": risk.get("sharpe"),
        "return_curve_basis": "reserved_initial_capital_v1",
    })
    output_dir.mkdir(parents=True, exist_ok=True)
    curve.to_csv(output_dir / "equity_curve.csv", index=False)
    build_drawdown_curve(curve).to_csv(output_dir / "drawdown_curve.csv", index=False)
    (output_dir / "strategy_performance.json").write_text(
        json.dumps(performance, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {
        "run_id": run_dir.name,
        "symbols": len(results),
        "dates": len(curve),
        "total_return": actual,
        "benchmark_return": benchmark_return,
        "excess_return": performance["excess_return_vs_benchmark"],
        "max_drawdown": performance["max_drawdown"],
        "first_date": dates.iloc[0],
        "last_date": dates.iloc[-1],
        "output_dir": str(output_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(rebuild(args.run_dir.resolve(), args.output_dir.resolve()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
