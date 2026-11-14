"""T5 真实脱敏快照与离线 Store 契约。"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

from quant_research_engine.game.data import PostgresGameDataProvider

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "game"))
from snapshot_store import SnapshotGameStore  # noqa: E402

SNAPSHOTS = ROOT / "data" / "game_snapshots"


def test_snapshot_store_six_methods_and_lengths():
    store = SnapshotGameStore(SNAPSHOTS)
    latest = store.latest_trade_date()
    assert isinstance(latest, date)
    assert store.qualified_table("public.stock_daily") == "public.stock_daily"
    symbols = store.list_symbols_with_bars(date(2000, 1, 1), latest)
    assert symbols == ["X00001B", "X00002B", "X00003B"]
    for symbol in symbols:
        bars = store.load_raw_bars(symbol, date(2000, 1, 1), latest)
        assert len(bars) == 1500
        assert {bar["ts_code"] for bar in bars} == {symbol}


def test_real_snapshot_creates_game_session_with_factors():
    store = SnapshotGameStore(SNAPSHOTS)
    session = PostgresGameDataProvider(store).create_session(seed=2026)

    assert len(session.bars) == 1500
    assert session.symbol in {"X00001B", "X00002B", "X00003B"}
    assert len(session.public_history()) == 250
    assert session.factor_audit["checked"] > 0
    # BOLL 只依赖窗口内数据，应逐点一致；EMA 在 1500 根截断面有种子差异，
    # 不能用全历史因子值反推截面首根的 SMA 种子，故不设全因子零误报假断言。
    for canonical, stats in session.factor_audit["canonicals"].items():
        if ".bb" in canonical:
            assert stats["mismatches"] == 0


def test_snapshots_do_not_leak_source_codes_or_real_dates():
    for path in SNAPSHOTS.glob("x*b.json"):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"[036]\d{5}\.(?:SH|SZ|BJ)", text) is None
        payload = json.loads(text)
        assert payload["symbol"] == path.stem.upper()
        assert len(payload["bars"]) == 1500
