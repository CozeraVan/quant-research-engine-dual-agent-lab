"""Windows 游戏修复的 WSL 入库回归（按 46 号文档契约重写）。

2026-11-14 增补（typical 691 误报根因轮）：
- 跨口径 EMA 缓存污染回归：close 先审计时 typical/average 的同名列不得
  复用 close 序列（非对称 bar，HLC3 ≠ close / VWAP ≠ close）；
- average_price 口径 VWAP→EMA 有效重算 + 无法识别公式 skipped；
- 恢复样本集成审计（f6385d8 契约）：SampleGameStore 非对称真实口径数据上
  typical 零误报、篡改必捕获——合成对称 bar（HLC3==close）抓不到该根因。
"""

from __future__ import annotations

import random
import re
import sys
from datetime import date
from pathlib import Path

import pytest

from quant_research_engine.core.models import Bar, OrderSide
from quant_research_engine.game import validation
from quant_research_engine.game.data import PostgresGameDataProvider
from quant_research_engine.game.engine import DailyGameEngine
from quant_research_engine.game.factors import DEFAULT_CANONICALS
from quant_research_engine.game.validation import audit_price_factors, recompute_ema

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "win"))

from game_preview_sample import SampleGameStore  # noqa: E402

CLOSE_EMA5 = DEFAULT_CANONICALS[0]
TYPICAL_EMA5 = "factors.stock_daily_overlap_typical_price.ema_5"


def _bars(count: int = 30) -> list[Bar]:
    return [
        Bar(
            symbol="X00001B",
            trade_date=date(2020, 1, 1),
            open=10.0 + index,
            high=11.0 + index,
            low=9.0 + index,
            close=10.0 + index,
            pre_close=9.0 + index,
            volume=1000.0,
            amount=10000.0,
        )
        for index in range(count)
    ]


@pytest.fixture()
def sample_provider():
    return PostgresGameDataProvider(SampleGameStore())


def test_typical_price_uses_hlc3_instead_of_close():
    bars = _bars()
    close_expected = recompute_ema([bar.close for bar in bars], 5)
    typical_expected = recompute_ema(
        [(bar.high + bar.low + bar.close) / 3 for bar in bars], 5
    )
    factors = {
        index: {CLOSE_EMA5: close_expected[index], TYPICAL_EMA5: typical_expected[index]}
        for index in range(4, len(bars))
    }

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5, TYPICAL_EMA5])

    assert audit["mismatches"] == 0
    assert audit["canonicals"][TYPICAL_EMA5]["checked"] == 10
    factors[len(bars) - 1][TYPICAL_EMA5] += 10.0
    audit = audit_price_factors(bars, factors, [CLOSE_EMA5, TYPICAL_EMA5])
    assert audit["canonicals"][TYPICAL_EMA5]["mismatches"] == 1


def test_typical_audit_not_poisoned_by_close_cache():
    """跨口径缓存污染回归（691 误报根因）：HLC3 ≠ close 的非对称 bar。

    close.ema_5 先审计会在共享缓存里留下 ("ema","5")→EMA(close)；
    typical.ema_5 若误配该序列，暖机后每个检查点都 mismatch。
    对称 bar（HLC3==close）无法区分两条序列，必须用非对称数据。
    """
    bars = [
        Bar(
            symbol="X00001B",
            trade_date=date(2020, 1, 1),
            open=10.0 + index,
            high=12.0 + index + (index % 3),
            low=9.0 + index,
            close=10.0 + index,
            pre_close=9.0 + index,
            volume=1000.0,
            amount=10000.0,
        )
        for index in range(30)
    ]
    close_expected = recompute_ema([bar.close for bar in bars], 5)
    typical_expected = recompute_ema(
        [(bar.high + bar.low + bar.close) / 3 for bar in bars], 5
    )
    # HLC3 = close + (1 + index%3)/3，与 close 持续偏离约 0.67（远超容差）
    factors = {
        index: {CLOSE_EMA5: close_expected[index], TYPICAL_EMA5: typical_expected[index]}
        for index in range(4, len(bars))
    }

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5, TYPICAL_EMA5])

    assert audit["canonicals"][TYPICAL_EMA5]["checked"] == 10
    assert audit["mismatches"] == 0, audit
    factors[len(bars) - 1][TYPICAL_EMA5] += 1.0
    audit = audit_price_factors(bars, factors, [CLOSE_EMA5, TYPICAL_EMA5])
    assert audit["canonicals"][TYPICAL_EMA5]["mismatches"] == 1


def test_injected_factor_corruption_is_caught():
    bars = _bars()
    expected = recompute_ema([bar.close for bar in bars], 5)
    factors = {index: {CLOSE_EMA5: expected[index]} for index in range(4, len(bars))}
    factors[len(bars) - 1][CLOSE_EMA5] += 1.0

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5])

    assert audit["checked"] == len(bars) - 20
    assert audit["mismatches"] == 1


def test_close_ema_recompute_matches_without_mismatch():
    bars = _bars()
    expected = recompute_ema([bar.close for bar in bars], 5)
    factors = {index: {CLOSE_EMA5: expected[index]} for index in range(4, len(bars))}

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5])

    assert audit["checked"] == len(bars) - 20
    assert audit["mismatches"] == 0


def test_unregistered_price_formula_is_skipped():
    canonical = "factors.stock_daily_overlap_close.unregistered_ema_999"
    audit = audit_price_factors(_bars(), {29: {canonical: 10.0}}, [canonical])

    assert audit["checked"] == 0
    assert audit["mismatches"] == 0
    assert audit["canonicals"][canonical]["skipped"] is True


def test_open_price_orders_fill_for_thirty_seeds():
    for seed in range(30):
        rng = random.Random(seed)
        open_price = round(rng.uniform(5.0, 100.0), 2)
        bar = Bar(
            symbol="X00001B",
            trade_date=date(2020, 1, 2),
            open=open_price,
            high=open_price + 1.0,
            low=max(0.01, open_price - 1.0),
            close=open_price,
            pre_close=open_price,
            volume=1000.0,
            amount=10000.0,
        )
        engine = DailyGameEngine(initial_cash=1_000_000.0)
        engine.create_order("X00001B", bar.trade_date, OrderSide.BUY, open_price, 100, open_price)

        fill = engine.settle_pending(bar)

        assert fill is not None
        assert fill.price == open_price
        assert fill.quantity == 100


def test_kv_grid_is_explicit_css_grid():
    template = Path("src/quant_research_engine/game/templates/game.html").read_text(
        encoding="utf-8"
    )

    assert re.search(r"\.kv-grid\s*\{[^}]*display\s*:\s*grid", template)
    assert re.search(r"\.side-card\s+\.kv-grid\s*\{[^}]*grid-template-columns", template)


def test_average_price_uses_bar_adjustment_ratio():
    from quant_research_engine.game.data import bars_from_rows
    from datetime import timedelta

    canonical = "factors.stock_daily_momentum_average_price.macd_12_26_9"
    rows = [
        {
            "ts_code": "X00001B",
            "trade_date": date(2020, 1, 1) + timedelta(days=index),
            "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0,
            "pre_close": 10.0, "vol": 100.0, "amount": 1000.0,
            "adj_factor": 1.0 if index == 0 else 2.0,
        }
        for index in range(2)
    ]
    bars = bars_from_rows(rows)

    assert bars[0].average_price == 50.0
    assert bars[1].average_price == 100.0
    audit = audit_price_factors(
        bars,
        {0: {canonical: 50.0}, 1: {canonical: 100.0}},
        [canonical],
    )
    # MACD 列无法由 VWAP 单序列重算 → 显式 skipped，不做猜测性比较
    assert audit["canonicals"][canonical]["skipped"] is True
    assert audit["mismatches"] == 0


def test_average_price_vwap_ema_audit_recomputes(monkeypatch):
    """average_price 口径有效重算：VWAP×复权比率 → EMA，逐点审计且篡改必捕获。

    注册表当前只有 momentum_average_price 的 MACD 列（不可重算→skipped），
    故 monkeypatch 登记 overlap_average_price.ema_5 验证审计契约本身；
    close 同批先审计，兼防跨口径缓存污染（与 typical 691 同一根因）。
    """
    avg_ema = "factors.stock_daily_overlap_average_price.ema_5"
    monkeypatch.setattr(validation, "factor_catalog", lambda: [
        {"canonical": CLOSE_EMA5, "column": "ema_5", "table": "stock_daily_overlap_close"},
        {"canonical": avg_ema, "column": "ema_5", "table": "stock_daily_overlap_average_price"},
    ])
    bars = [
        Bar(
            symbol="X00001B",
            trade_date=date(2020, 1, 1),
            open=10.0 + index,
            high=12.0 + index,
            low=9.0 + index,
            close=10.0 + index,
            pre_close=9.0 + index,
            volume=100.0,
            amount=200.0 + 5.0 * index,
            adjustment_ratio=0.5,
        )
        for index in range(30)
    ]
    # VWAP = amount*10/vol × ratio = (20 + 0.5i) × 0.5 = 10 + 0.25i ≠ close
    vwap_expected = recompute_ema([bar.average_price for bar in bars], 5)
    close_expected = recompute_ema([bar.close for bar in bars], 5)
    factors = {
        index: {CLOSE_EMA5: close_expected[index], avg_ema: vwap_expected[index]}
        for index in range(4, len(bars))
    }

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5, avg_ema])

    assert audit["canonicals"][avg_ema]["checked"] == 10
    assert audit["mismatches"] == 0, audit
    factors[len(bars) - 1][avg_ema] += 5.0
    audit = audit_price_factors(bars, factors, [CLOSE_EMA5, avg_ema])
    assert audit["canonicals"][avg_ema]["mismatches"] == 1


def test_ema_seed_warmup_does_not_hide_isolated_anomaly():
    canonical = DEFAULT_CANONICALS[3]
    bars = _bars(1500)
    expected = recompute_ema([bar.close for bar in bars], 250)
    factors = {}
    for index in range(249, len(bars)):
        # 模拟全历史 EMA 与窗口新鲜 SMA 种子的指数衰减差，末段应收敛。
        decay = (1 - 2 / 251) ** index
        factors[index] = {canonical: expected[index] + 100 * decay}
    audit = audit_price_factors(bars, factors, [canonical])
    assert audit["mismatches"] == 0
    assert audit["checked"] == 500

    factors[len(bars) - 2][canonical] += 10.0
    audit = audit_price_factors(bars, factors, [canonical])
    assert audit["mismatches"] == 1


# ---------------- 样本集成审计（f6385d8 契约：非对称真实口径数据零误报）
# 合成样本因子按 hfq 全历史计算、provider 按锚点换算 qfq；审计窗口即全历史，
# EMA 种子同源，正常时残差仅 round(…,4)/anchor 量级（≤5e-5），远低于容差。


def test_sample_audit_typical_zero_mismatch(sample_provider):
    """样本上 typical 审计零误报（2026-11-14 根因回归）。

    跨口径 EMA 缓存污染曾在此制造 691 处误报：checked=11383、
    max_abs_diff≈0.17017、max_rel_diff≈0.0088942，全部落在 typical.ema_5
    的 index 20..1599 全域（非暖机集中、非上游异常）。
    """
    session = sample_provider.create_session(seed=7)
    sample_provider.load_selected(session, (*DEFAULT_CANONICALS, TYPICAL_EMA5))
    audit = session.factor_audit
    assert TYPICAL_EMA5 in audit["canonicals"], "typical 口径应被审计而非忽略"
    assert audit["canonicals"][TYPICAL_EMA5]["checked"] > 0
    assert audit["mismatches"] == 0, audit


def test_sample_audit_still_catches_corrupted_typical(sample_provider):
    session = sample_provider.create_session(seed=7)
    sample_provider.load_selected(session, (*DEFAULT_CANONICALS, TYPICAL_EMA5))
    for values in session.factors.values():
        if TYPICAL_EMA5 in values:
            values[TYPICAL_EMA5] += 1.0
    audit = audit_price_factors(
        session.bars, session.factors, session.selected_canonicals)
    assert audit["canonicals"][TYPICAL_EMA5]["mismatches"] > 0, "审计不得因修复而失效"


def test_sample_audit_close_basis_zero_mismatch(sample_provider):
    session = sample_provider.create_session(seed=7)
    audit = session.factor_audit
    assert audit["checked"] > 0
    assert audit["mismatches"] == 0, audit
