#!/usr/bin/env python3
"""Generate a normalized Alpha191 rank-strategy YAML without running a backtest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.strategies.alpha191 import build_alpha191_rank_strategy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alpha", help="alpha001…alpha191")
    parser.add_argument("--direction", choices=("high", "low"), default="high")
    parser.add_argument("--entry", type=float)
    parser.add_argument("--exit", dest="exit_", type=float)
    parser.add_argument("--holding-days", type=int, default=10)
    parser.add_argument("--stop-loss", type=float, default=0.08)
    parser.add_argument("--name")
    parser.add_argument("--output", type=Path, help="写入新文件；默认输出 stdout，已有文件不覆盖")
    args = parser.parse_args()
    raw = build_alpha191_rank_strategy(
        args.alpha, direction=args.direction, entry_threshold=args.entry,
        exit_threshold=args.exit_, holding_days=args.holding_days,
        stop_loss_pct=args.stop_loss, name=args.name,
    )
    text = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)
    if args.output is None:
        print(text, end="")
    else:
        if args.output.exists():
            parser.error(f"文件已存在，不覆盖：{args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
