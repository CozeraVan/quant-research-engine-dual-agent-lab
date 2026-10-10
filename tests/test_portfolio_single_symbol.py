import pandas as pd
import pytest

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestRequest, SingleSymbolBacktestEngine


def make_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 6,
            "trade_date": pd.to_datetime(
                ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]
            ),
            "open": [10.0, 10.2, 10.5, 10.8, 11.0, 11.2],
            "close": [10.1, 10.4, 10.7, 10.9, 11.1, 11.3],
            "rsi_2": [5.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        }
    )


def test_single_symbol_backtest_buys_next_open_and_sells_after_holding_days():
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_frame(), request)

    assert result.orders[["trade_date", "side", "quantity", "price"]].to_dict("records") == [
        {"trade_date": pd.Timestamp("2026-01-06"), "side": "buy", "quantity": 9800, "price": 10.2},
        {"trade_date": pd.Timestamp("2026-01-09"), "side": "sell", "quantity": 9800, "price": 11.0},
    ]
    assert result.trades[["entry_date", "exit_date", "quantity", "entry_price", "exit_price"]].to_dict("records") == [
        {
            "entry_date": pd.Timestamp("2026-01-06"),
            "exit_date": pd.Timestamp("2026-01-09"),
            "quantity": 9800,
            "entry_price": 10.2,
            "exit_price": 11.0,
        }
    ]


def test_single_symbol_backtest_summary_accounts_for_costs():
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_frame(), request)
    summary = result.summary

    assert summary["trade_count"] == 1
    assert summary["win_rate"] == 1.0
    assert summary["final_equity"] == pytest.approx(107721.6944)
    assert summary["total_return"] == pytest.approx(0.077216944)
    assert summary["total_cost"] == pytest.approx(118.3056)


def test_single_symbol_backtest_records_daily_equity():
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_frame(), request)

    assert len(result.equity_curve) == 6
    assert result.equity_curve.iloc[-1]["total_equity"] == pytest.approx(result.summary["final_equity"])


def test_single_symbol_backtest_does_not_enter_when_next_bar_missing():
    frame = make_frame().iloc[:1]
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)

    assert result.orders.empty
    assert result.trades.empty
    assert result.summary["trade_count"] == 0


def test_single_symbol_backtest_records_failed_buy_when_limit_up():
    frame = make_frame()
    frame["limit_up"] = [False, True, False, False, False, False]
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)

    assert result.orders.empty
    assert result.trades.empty
    assert result.failed_orders[["trade_date", "side", "reason"]].to_dict("records") == [
        {"trade_date": pd.Timestamp("2026-01-06"), "side": "buy", "reason": "limit_up_buy_blocked"}
    ]


def test_single_symbol_backtest_infers_failed_buy_when_open_is_limit_up():
    frame = make_frame()
    frame["pre_close"] = [9.8, 9.2727, 10.4, 10.7, 10.9, 11.1]
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)

    assert result.orders.empty
    assert result.failed_orders.iloc[0]["reason"] == "limit_up_buy_blocked"


def test_single_symbol_backtest_records_failed_sell_when_limit_down():
    frame = make_frame()
    frame["limit_down"] = [False, False, False, False, True, False]
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)

    assert len(result.orders) == 2
    assert result.failed_orders[["trade_date", "side", "reason"]].to_dict("records") == [
        {"trade_date": pd.Timestamp("2026-01-09"), "side": "sell", "reason": "limit_down_sell_blocked"}
    ]


def test_single_symbol_backtest_retries_sell_after_limit_down_failure():
    frame = make_frame()
    frame["limit_down"] = [False, False, False, False, True, False]
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)

    assert result.orders.iloc[-1]["side"] == "sell"
    assert result.orders.iloc[-1]["trade_date"] == pd.Timestamp("2026-01-12")
    assert len(result.trades) == 1
    assert result.failed_orders.iloc[0]["reason"] == "limit_down_sell_blocked"


def test_single_symbol_backtest_can_enter_again_after_completed_trade():
    frame = make_frame()
    frame.loc[4, "rsi_2"] = 5.0
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=1,
    )

    result = engine.run(frame, request)

    assert result.orders["side"].tolist() == ["buy", "sell", "buy"]
    assert result.orders.iloc[2]["trade_date"] == pd.Timestamp("2026-01-12")


def test_single_symbol_backtest_uses_market_profile_slippage_prices():
    engine = SingleSymbolBacktestEngine(
        market_profile=AShareMarketProfile(slippage_buy_rate=0.001, slippage_sell_rate=0.002)
    )
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_frame(), request)

    assert result.orders.iloc[0]["price"] == pytest.approx(10.2102)
    assert result.orders.iloc[1]["price"] == pytest.approx(10.978)


def test_single_symbol_backtest_summary_includes_buy_hold_return():
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_frame(), request)
    summary = result.summary

    # first open=10.0, last close=11.3 → buy_hold_return = 11.3/10.0 - 1 = 0.13
    assert summary["buy_hold_return"] == pytest.approx(0.13)
    # strategy total_return is ~0.0772, so excess is negative
    assert summary["excess_return_vs_buy_hold"] == pytest.approx(0.077216944 - 0.13)


def test_single_symbol_backtest_buy_hold_return_is_none_for_empty_frame():
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="NOT_FOUND",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_frame(), request)

    assert result.summary["buy_hold_return"] is None
    assert result.summary["excess_return_vs_buy_hold"] is None


def test_single_symbol_backtest_sells_on_exit_signal_next_bar():
    frame = make_frame().copy()
    frame["entry_flag"] = [True, False, False, False, False, False]
    frame["exit_flag"] = [False, False, True, False, False, False]
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="entry_flag",
        holding_days=20,
        exit_signal="exit_flag",
    )

    result = engine.run(frame, request)

    assert result.orders[["trade_date", "side"]].to_dict("records") == [
        {"trade_date": pd.Timestamp("2026-01-06"), "side": "buy"},
        {"trade_date": pd.Timestamp("2026-01-08"), "side": "sell"},
    ]
    assert result.trades.iloc[0]["exit_reason"] == "exit_signal"


def test_single_symbol_backtest_holding_days_zero_means_unlimited():
    """holding_days=0 = 不限持仓天数：无 exit_signal 时持有到数据末尾，
    不触发 holding_period 强平（与 max_positions=0=不限 语义对齐）。"""
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=0,
    )

    result = engine.run(make_frame(), request)

    # 只有买入单，持仓到末尾，无任何卖出/trade
    assert [o["side"] for o in result.orders.to_dict("records")] == ["buy"]
    assert result.trades.empty
    assert result.equity_curve.iloc[-1]["position_quantity"] > 0


def test_single_symbol_backtest_holding_days_zero_still_honors_exit_signal():
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        exit_signal="rsi_2 > 40",
        holding_days=0,
    )

    result = engine.run(make_frame(), request)

    assert len(result.trades) == 1
    assert result.trades.iloc[0]["exit_reason"] == "exit_signal"
    # 买入 01-06；rsi_2>40 首次出现在 01-09(50)，下一根 01-12 按 open 成交
    assert result.trades.iloc[0]["exit_date"] == pd.Timestamp("2026-01-12")


def test_single_symbol_backtest_holding_days_negative_rejected():
    engine = SingleSymbolBacktestEngine(market_profile=AShareMarketProfile())
    request = SingleSymbolBacktestRequest(
        symbol="000001.SZ",
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=-1,
    )
    with pytest.raises(ValueError, match=">= 0"):
        engine.run(make_frame(), request)
