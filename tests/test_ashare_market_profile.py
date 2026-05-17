from datetime import date
import pytest

from quant_research_engine.core.models import Order, OrderSide, OrderType
from quant_research_engine.markets.ashare import AShareMarketProfile


def test_ashare_buy_quantity_is_rounded_down_to_lot_size():
    profile = AShareMarketProfile()

    assert profile.round_order_quantity(OrderSide.BUY, 260) == 200


def test_ashare_sell_quantity_allows_odd_lot_by_default():
    profile = AShareMarketProfile()

    assert profile.round_order_quantity(OrderSide.SELL, 260) == 260


def test_ashare_costs_apply_commission_minimum_and_sell_stamp_tax():
    profile = AShareMarketProfile(
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_tax_sell=0.0005,
        transfer_fee_rate=0.00001,
    )

    buy_cost = profile.calculate_cost(side=OrderSide.BUY, notional=10000.0)
    sell_cost = profile.calculate_cost(side=OrderSide.SELL, notional=10000.0)

    assert buy_cost == 5.1
    assert sell_cost == 10.1


def test_ashare_rejects_buy_when_limit_up_blocked():
    profile = AShareMarketProfile()
    order = Order(
        symbol="000001.SZ",
        trade_date=date(2026, 5, 12),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        price=11.0,
    )

    result = profile.validate_order(order, is_suspended=False, limit_up=True, limit_down=False)

    assert not result.allowed
    assert result.reason == "limit_up_buy_blocked"


def test_ashare_rejects_sell_when_limit_down_blocked():
    profile = AShareMarketProfile()
    order = Order(
        symbol="000001.SZ",
        trade_date=date(2026, 5, 12),
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=100,
        price=9.0,
    )

    result = profile.validate_order(order, is_suspended=False, limit_up=False, limit_down=True)

    assert not result.allowed
    assert result.reason == "limit_down_sell_blocked"


def test_ashare_gets_price_limit_rate_by_symbol():
    profile = AShareMarketProfile()

    assert profile.get_price_limit_rate("000001.SZ") == 0.10
    assert profile.get_price_limit_rate("300001.SZ") == 0.20
    assert profile.get_price_limit_rate("688001.SH") == 0.20
    assert profile.get_price_limit_rate("920001.BJ") == 0.30
    assert profile.get_price_limit_rate("000001.SZ", is_st=True) == 0.05


def test_ashare_detects_limit_up_and_down_from_pre_close_and_price():
    profile = AShareMarketProfile()

    assert profile.is_limit_up("000001.SZ", pre_close=10.0, price=11.0)
    assert profile.is_limit_down("000001.SZ", pre_close=10.0, price=9.0)
    assert not profile.is_limit_up("000001.SZ", pre_close=10.0, price=10.98)
    assert profile.is_limit_up("300001.SZ", pre_close=10.0, price=12.0)


def test_ashare_applies_percent_slippage_to_execution_price():
    profile = AShareMarketProfile(slippage_buy_rate=0.001, slippage_sell_rate=0.002)

    assert profile.apply_slippage(OrderSide.BUY, 10.0) == pytest.approx(10.01)
    assert profile.apply_slippage(OrderSide.SELL, 10.0) == pytest.approx(9.98)
