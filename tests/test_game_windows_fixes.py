"""Windows 游戏修复的 WSL 入库回归（按 46 号文档契约重写）。"""

from __future__ import annotations

import random
import re
from datetime import date
from pathlib import Path

from quant_research_engine.core.models import Bar, OrderSide
from quant_research_engine.game.engine import DailyGameEngine
from quant_research_engine.game.factors import DEFAULT_CANONICALS
from quant_research_engine.game.validation import audit_price_factors, recompute_ema

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


def test_typical_price_basis_has_no_close_recompute_false_positive():
    bars = _bars()
    expected = recompute_ema([bar.close for bar in bars], 5)
    factors = {
        index: {CLOSE_EMA5: expected[index], TYPICAL_EMA5: 999.0}
        for index in range(4, len(bars))
    }

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5, TYPICAL_EMA5])

    assert audit["mismatches"] == 0
    assert TYPICAL_EMA5 not in audit["canonicals"]


def test_injected_factor_corruption_is_caught():
    bars = _bars()
    expected = recompute_ema([bar.close for bar in bars], 5)
    factors = {index: {CLOSE_EMA5: expected[index]} for index in range(4, len(bars))}
    factors[len(bars) - 1][CLOSE_EMA5] += 1.0

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5])

    assert audit["checked"] == len(bars) - 4
    assert audit["mismatches"] == 1


def test_close_ema_recompute_matches_without_mismatch():
    bars = _bars()
    expected = recompute_ema([bar.close for bar in bars], 5)
    factors = {index: {CLOSE_EMA5: expected[index]} for index in range(4, len(bars))}

    audit = audit_price_factors(bars, factors, [CLOSE_EMA5])

    assert audit["checked"] == len(bars) - 4
    assert audit["mismatches"] == 0


def test_unregistered_price_formula_is_skipped():
    canonical = "factors.stock_daily_overlap_close.unregistered_ema_999"
    audit = audit_price_factors(_bars(), {29: {canonical: 10.0}}, [canonical])

    assert audit["checked"] == 0
    assert audit["mismatches"] == 0
    assert audit["canonicals"] == {}


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
    assert audit["mismatches"] == 0
