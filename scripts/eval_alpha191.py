#!/usr/bin/env python3
"""Alpha191 赚钱效应评估 CLI（factors.stock_daily_alpha191 面板因子库）。

Usage:
  uv run python scripts/eval_alpha191.py \
      [--start S] [--end E] [--factors alpha001,alpha002|all] \
      [--top N] [--output outputs/alpha191/leaderboard.csv] [--db-url URL]

默认评估近 2 年（R-QRE-009：先小样本验证口径，再全期）。leaderboard 列：
factor, mean_rank_ic(h=5), icir, ic_win_rate(方向一致率), top_minus_bottom(h=5,
Q5-Q1：做多最高五分位/做空最低五分位), observation_dates, significant(★:
|rank_ic|>=0.05 且胜率>=0.55)。按 |mean_rank_ic| 降序。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.evaluation.alpha191 import (
    ALL_ALPHA_FACTORS,
    AlphaEvalConfig,
    build_leaderboard,
    evaluate_alpha_factors,
)

DEFAULT_OUTPUT = ROOT / "outputs" / "alpha191" / "leaderboard.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpha191 赚钱效应评估（leaderboard 输出）")
    today = date.today()
    parser.add_argument("--start", default=str(today - timedelta(days=730)), help="开始日期 YYYY-MM-DD（默认近 2 年）")
    parser.add_argument("--end", default=str(today), help="结束日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--factors", default="all", help="逗号分隔因子名（alpha001,alpha006）或 all")
    parser.add_argument("--top", type=int, default=20, help="stdout 打印前 N 行（默认 20，CSV 始终全量）")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="leaderboard CSV 输出路径")
    parser.add_argument("--batch-size", type=int, default=10, help="每批取数因子数（默认 10）")
    parser.add_argument("--db-url", default=None, help="数据库 URL（默认 QRE_MARKET_DB_URL/SR_MARKET_DB_URL）")
    return parser.parse_args(argv)


def resolve_factors(spec: str) -> list[str]:
    if spec.strip().lower() == "all":
        return list(ALL_ALPHA_FACTORS)
    factors = [item.strip() for item in spec.split(",") if item.strip()]
    unknown = [f for f in factors if f not in ALL_ALPHA_FACTORS]
    if unknown:
        raise ValueError(f"未知 alpha191 因子: {unknown}（合法范围 alpha001..alpha191）")
    return factors


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    factors = resolve_factors(args.factors)
    config = AlphaEvalConfig(
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        batch_size=args.batch_size,
    )
    settings = DatabaseSettings(market_db_url=args.db_url) if args.db_url else DatabaseSettings.from_env()
    store = PostgresDataStore(settings)
    store.ping()
    try:
        print(f"评估 {len(factors)} 个因子，窗口 {config.start} ~ {config.end}，批次 {config.batch_size}")
        rows = evaluate_alpha_factors(store, factors, config)
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()

    board = build_leaderboard(rows)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output_path, index=False)
    print(f"\nleaderboard 已写入 {output_path}（{len(board)} 行）")

    top = board.head(args.top)
    if not top.empty:
        print(f"\nTop {len(top)}（按 |mean_rank_ic| 降序，h=5）：")
        print(top.to_string(index=False))
    n_star = int((board["significant"] == "★").sum()) if not board.empty else 0
    print(f"\n显著（★：|rank_ic|>=0.05 且方向一致率>=0.55）：{n_star} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
