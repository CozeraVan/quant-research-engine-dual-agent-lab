from datetime import date

from quant_research_engine.core.models import (
    AccountSnapshot,
    Bar,
    Instrument,
    InstrumentType,
    Order,
    OrderSide,
    OrderType,
)


def test_instrument_keeps_market_and_type_separate():
    instrument = Instrument(symbol="000001.SZ", market="ashare", type=InstrumentType.STOCK)

    assert instrument.symbol == "000001.SZ"
    assert instrument.market == "ashare"
    assert instrument.type is InstrumentType.STOCK


def test_bar_exposes_ohlcv_for_one_instrument_and_date():
    bar = Bar(
        symbol="000001.SZ",
        trade_date=date(2026, 5, 11),
        open=10.0,
        high=10.5,
        low=9.8,
        close=10.2,
        volume=1000000,
        amount=10200000,
        pre_close=10.0,
    )

    assert bar.symbol == "000001.SZ"
    assert bar.trade_date == date(2026, 5, 11)
    assert bar.close == 10.2
    assert bar.pre_close == 10.0


def test_order_notional_uses_price_and_quantity():
    order = Order(
        symbol="000001.SZ",
        trade_date=date(2026, 5, 12),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=300,
        price=10.25,
    )

    assert order.notional == 3075.0


def test_account_snapshot_total_equity_adds_cash_and_market_value():
    snapshot = AccountSnapshot(
        trade_date=date(2026, 5, 12),
        cash=100000.0,
        market_value=25000.0,
    )

    assert snapshot.total_equity == 125000.0
