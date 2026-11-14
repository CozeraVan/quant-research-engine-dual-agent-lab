"""零数据库的《我不是股神》快照 Store，与 SampleGameStore 六方法同构。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd


class SnapshotGameStore:
    settings = SimpleNamespace(
        tables=SimpleNamespace(market_daily_table="public.stock_daily")
    )

    def __init__(self, snapshot_dir: str | Path | None = None) -> None:
        root = snapshot_dir or Path(__file__).resolve().parents[2] / "data" / "game_snapshots"
        self.snapshot_dir = Path(root)
        paths = sorted(self.snapshot_dir.glob("x*b.json"))
        if not paths:
            raise ValueError(f"没有游戏快照：{self.snapshot_dir}")
        self._snapshots: dict[str, dict[str, Any]] = {}
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            symbol = payload["symbol"]
            self._snapshots[symbol] = payload

    def qualified_table(self, name: str) -> str:
        return name

    def latest_trade_date(self) -> date:
        return max(
            date.fromisoformat(bar["trade_date"])
            for payload in self._snapshots.values()
            for bar in payload["bars"][-1:]
        )

    def list_symbols_with_bars(self, start: date, end: date) -> list[str]:
        return [
            symbol
            for symbol, payload in self._snapshots.items()
            if any(start <= date.fromisoformat(bar["trade_date"]) <= end for bar in payload["bars"])
        ]

    def load_raw_bars(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        payload = self._snapshots[symbol]
        return [
            {**bar, "trade_date": date.fromisoformat(bar["trade_date"])}
            for bar in payload["bars"]
            if start <= date.fromisoformat(bar["trade_date"]) <= end
        ]

    def load_factor_history(self, symbols, requests, start, end) -> pd.DataFrame:
        names = [request.logical_name for request in requests]
        records: list[dict[str, Any]] = []
        for symbol in symbols:
            payload = self._snapshots[symbol]
            for source in payload.get("factors", []):
                day = date.fromisoformat(source["trade_date"])
                if not start <= day <= end:
                    continue
                row = {"ts_code": symbol, "trade_date": pd.Timestamp(day)}
                for name in names:
                    row[name] = source.get(name)
                records.append(row)
        return pd.DataFrame(records, columns=["ts_code", "trade_date", *names])
