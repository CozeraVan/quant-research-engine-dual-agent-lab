from datetime import date

import pytest

from quant_research_engine.core.models import Bar, OrderSide
from quant_research_engine.game.engine import DailyGameEngine, GameRuleError, price_limits


def bar(close=10.0, low=9.0, high=11.0, open_=10.0):
    return Bar(symbol="600000.SH", trade_date=date(2024, 1, 2), open=open_, high=high,
               low=low, close=close, pre_close=10.0, volume=1000)


def test_price_limits_match_order_validation():
    assert price_limits(10.0) == (9.0, 11.0)
    engine = DailyGameEngine()
    with pytest.raises(GameRuleError, match="±10%"):
        engine.create_order("600000.SH", date(2024, 1, 2), OrderSide.BUY, 11.01, 100, 10.0)


def test_buy_fill_and_t_plus_one_sellable():
    engine = DailyGameEngine()
    engine.create_order("600000.SH", date(2024, 1, 2), OrderSide.BUY, 10.0, 100, 10.0)
    fill = engine.settle_pending(bar())
    assert fill.price == 10.0 and engine.quantity == 100 and engine.sellable == 0
    engine.close_day(bar())
    assert engine.sellable == 100 and engine.total_cost > 0


def test_cancel_order_has_no_account_effect():
    engine = DailyGameEngine()
    engine.create_order("600000.SH", date(2024, 1, 2), OrderSide.BUY, 10.0, 100, 10.0)
    engine.cancel_order()
    assert engine.pending_order is None and engine.cash == 1_000_000 and engine.quantity == 0
    assert engine.events[-1]["type"] == "cancelled"
    with pytest.raises(GameRuleError, match="没有可撤销"):
        engine.cancel_order()


def test_untouched_order_does_not_fill():
    engine = DailyGameEngine()
    engine.create_order("600000.SH", date(2024, 1, 2), OrderSide.BUY, 9.5, 100, 10.0)
    assert engine.settle_pending(bar(low=9.6)) is None
    assert engine.quantity == 0 and engine.events[-1]["reason"] == "price_not_touched"


def test_one_word_limit_up_blocks_buy():
    engine = DailyGameEngine()
    engine.create_order("600000.SH", date(2024, 1, 2), OrderSide.BUY, 11.0, 100, 10.0)
    assert engine.settle_pending(bar(close=11.0, low=11.0, high=11.0, open_=11.0)) is None
    assert engine.events[-1]["reason"] == "one_word_limit"


def test_sell_uses_t_plus_one_inventory():
    engine = DailyGameEngine()
    with pytest.raises(GameRuleError, match="可卖持仓不足"):
        engine.create_order("600000.SH", date(2024, 1, 2), OrderSide.SELL, 10.0, 100, 10.0)
