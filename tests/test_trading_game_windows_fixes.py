"""Windows 侧 game 回归测试（任务单 docs/agent/46_GAME_WINDOWS_TASKS_2026-11-12.md）。

T1：样本 vol/amount 生产单位（手/千元），逐根均价区间断言；
T2：f6385d8 修复切片 6 项 RED→GREEN 测试并入（原 .tmp scratch，不再是回归资产）；
T3：game 状态显式返回 factor_basis（引用 factor_basis 契约常量，不造第二套口径）；
T4：average_price 公式登记但审计保持 skipped（Bar 无复权比率，禁止冒充前复权均价）。

本文件属 46 号 §2/§7 允许的「本轮新增 game 测试」；不改动既有测试。
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "win"))

from game_preview_sample import N_DAYS, SampleGameStore  # noqa: E402


def test_sample_vol_amount_production_units():
    """T1：vol=手（1 手=100 股）、amount=千元；逐根 amount*10/vol ∈ [low, high]。

    均价（元/股）= amount×1000 元 / (vol×100 股) = amount*10/vol。
    样本若按「股/元」造，该比值是真实均价的 10 倍，必然越出当日区间。
    逐根校验全部标的全部 bar，不是抽查。
    """
    store = SampleGameStore()
    end = store.latest_trade_date()
    start = end - timedelta(days=4000)  # 覆盖 N_DAYS 个交易日（约 2240 自然日）
    symbols = store.list_symbols_with_bars(start, end)
    assert symbols, "样本必须有标的"
    checked = 0
    for symbol in symbols:
        rows = store.load_raw_bars(symbol, start, end)
        assert len(rows) == N_DAYS
        for row in rows:
            assert row["vol"] > 0
            average_price = row["amount"] * 10.0 / row["vol"]
            assert row["low"] <= average_price <= row["high"], (
                symbol, row["trade_date"], average_price, row["low"], row["high"])
            # 均价还须落在当日真实价格水平：防 vol/amount 同倍率缩放骗过区间断言
            assert abs(average_price - (row["open"] + row["close"]) / 2.0) < 0.01, (
                symbol, row["trade_date"], average_price)
            checked += 1
    assert checked == N_DAYS * len(symbols)