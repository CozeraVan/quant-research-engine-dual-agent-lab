import pandas as pd
import pytest

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest


def make_shared_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 5 + ["000002.SZ"] * 5,
            "trade_date": pd.to_datetime(
                [
                    "2026-01-05",
                    "2026-01-06",
                    "2026-01-07",
                    "2026-01-08",
                    "2026-01-09",
                ]
                * 2
            ),
            "open": [10.0, 10.2, 10.5, 10.8, 11.0, 20.0, 19.8, 19.5, 19.0, 18.8],
            "close": [10.1, 10.4, 10.7, 10.9, 11.1, 19.9, 19.7, 19.3, 18.9, 18.7],
            "rsi_2": [5.0, 20.0, 30.0, 40.0, 50.0, 5.0, 20.0, 30.0, 40.0, 50.0],
            "signal_score": [1.0, 1.0, 1.0, 1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        }
    )


def test_shared_cash_backtest_buys_multiple_signals_with_one_cash_pool():
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
    )

    result = engine.run(make_shared_frame(), request)

    assert result.orders[["trade_date", "symbol", "side"]].to_dict("records") == [
        {"trade_date": pd.Timestamp("2026-01-06"), "symbol": "000001.SZ", "side": "buy"},
        {"trade_date": pd.Timestamp("2026-01-06"), "symbol": "000002.SZ", "side": "buy"},
        {"trade_date": pd.Timestamp("2026-01-08"), "symbol": "000001.SZ", "side": "sell"},
        {"trade_date": pd.Timestamp("2026-01-08"), "symbol": "000002.SZ", "side": "sell"},
    ]
    assert result.trades["symbol"].tolist() == ["000001.SZ", "000002.SZ"]
    assert result.equity_curve.iloc[1]["position_count"] == 2
    assert result.summary["trade_count"] == 2
    assert result.summary["initial_cash"] == 100000.0
    assert result.orders.loc[result.orders["side"] == "buy", "notional"].sum() > 90000


def test_shared_cash_backtest_sells_on_exit_signal_next_bar():
    frame = make_shared_frame().copy()
    frame["entry_flag"] = [True, False, False, False, False] * 2
    frame["exit_flag"] = [False, False, True, False, False] * 2
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="entry_flag",
        holding_days=20,
        max_positions=2,
        exit_signal="exit_flag",
    )

    result = engine.run(frame, request)
    trade = result.trades.loc[result.trades["symbol"] == "000001.SZ"].iloc[0]

    assert result.orders.loc[result.orders["symbol"] == "000001.SZ", "side"].tolist() == ["buy", "sell"]
    assert trade["exit_reason"] == "exit_signal"


def test_shared_cash_backtest_respects_max_positions():
    frame = make_shared_frame()
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=1,
    )

    result = engine.run(frame, request)

    assert result.orders[result.orders["side"] == "buy"]["symbol"].tolist() == ["000001.SZ"]
    assert result.summary["trade_count"] == 1


def test_shared_cash_backtest_rejects_invalid_max_positions():
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=0,
    )

    with pytest.raises(ValueError, match="max_positions must be positive"):
        engine.run(make_shared_frame(), request)


def test_shared_cash_backtest_can_size_entries_by_score_weight():
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
    )

    result = engine.run(make_shared_frame(), request)
    buys = result.orders.loc[result.orders["side"] == "buy"].set_index("symbol")

    assert buys.loc["000002.SZ", "notional"] > buys.loc["000001.SZ", "notional"]


def test_shared_cash_backtest_rebalances_existing_positions_on_fixed_interval():
    frame = make_shared_frame()
    frame["open"] = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0]
    frame["close"] = frame["open"]
    frame["signal_score"] = [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0]
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=120000.0,
        entry_signal="rsi_2 < 10",
        holding_days=4,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=2,
    )

    result = engine.run(frame, request)
    rebalance_orders = result.orders.loc[
        (result.orders["reason"] == "rebalance")
        & (result.orders["trade_date"] == pd.Timestamp("2026-01-07"))
    ]

    assert rebalance_orders[["trade_date", "symbol", "side"]].to_dict("records") == [
        {"trade_date": pd.Timestamp("2026-01-07"), "symbol": "000002.SZ", "side": "sell"},
        {"trade_date": pd.Timestamp("2026-01-07"), "symbol": "000001.SZ", "side": "buy"},
    ]
    buys = result.orders.loc[result.orders["side"] == "buy"].set_index(["trade_date", "symbol"])
    assert buys.loc[(pd.Timestamp("2026-01-07"), "000001.SZ"), "quantity"] > 0


def test_shared_cash_backtest_reports_rebalance_summary_metrics():
    frame = make_shared_frame()
    frame["open"] = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0]
    frame["close"] = frame["open"]
    frame["signal_score"] = [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0]
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=120000.0,
        entry_signal="rsi_2 < 10",
        holding_days=4,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=2,
    )

    result = engine.run(frame, request)
    rebalance_orders = result.orders.loc[result.orders["reason"] == "rebalance"]
    average_equity = result.equity_curve["total_equity"].mean()

    assert result.summary["rebalance_order_count"] == len(rebalance_orders)
    assert result.summary["rebalance_notional"] == pytest.approx(float(rebalance_orders["notional"].sum()))
    assert result.summary["rebalance_cost"] == pytest.approx(float(rebalance_orders["cost"].sum()))
    assert result.summary["rebalance_turnover"] == pytest.approx(
        float(rebalance_orders["notional"].sum()) / average_equity
    )


def test_shared_cash_backtest_records_rebalance_sell_realized_pnl():
    frame = make_shared_frame()
    frame["open"] = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0]
    frame["close"] = frame["open"]
    frame["signal_score"] = [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0]
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=120000.0,
        entry_signal="rsi_2 < 10",
        holding_days=4,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=2,
    )

    result = engine.run(frame, request)
    rebalance_sell = result.orders.loc[
        (result.orders["reason"] == "rebalance")
        & (result.orders["side"] == "sell")
        & (result.orders["trade_date"] == pd.Timestamp("2026-01-07"))
        & (result.orders["symbol"] == "000002.SZ")
    ].iloc[0]
    rebalance_trade = result.trades.loc[
        (result.trades["exit_reason"] == "rebalance")
        & (result.trades["exit_date"] == pd.Timestamp("2026-01-07"))
        & (result.trades["symbol"] == "000002.SZ")
    ].iloc[0]

    assert rebalance_trade["quantity"] == rebalance_sell["quantity"]
    assert rebalance_trade["entry_price"] == pytest.approx(20.0)
    assert rebalance_trade["exit_price"] == pytest.approx(20.0)
    assert rebalance_trade["gross_pnl"] == pytest.approx(0.0)
    assert rebalance_trade["cost"] > rebalance_sell["cost"]
    assert rebalance_trade["net_pnl"] < 0.0


def test_shared_cash_rebalance_partial_sell_uses_fifo_lot_cost_basis():
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 5 + ["000002.SZ"] * 5,
            "trade_date": pd.to_datetime(
                [
                    "2026-01-05",
                    "2026-01-06",
                    "2026-01-07",
                    "2026-01-08",
                    "2026-01-09",
                ]
                * 2
            ),
            "open": [10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0],
            "close": [10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0],
            "rsi_2": [5.0, 20.0, 20.0, 20.0, 20.0, 5.0, 20.0, 20.0, 20.0, 20.0],
            "signal_score": [1.0, 1.0, 10.0, 1.0, 1.0, 1.0, 1.0, 1.0, 10.0, 10.0],
        }
    )
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=10,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=1,
    )

    result = engine.run(frame, request)
    rebalance_trade = result.trades.loc[
        (result.trades["symbol"] == "000001.SZ")
        & (result.trades["exit_reason"] == "rebalance")
        & (result.trades["exit_date"] == pd.Timestamp("2026-01-08"))
    ].iloc[0]
    first_buy_quantity = int(
        result.orders.loc[
            (result.orders["symbol"] == "000001.SZ")
            & (result.orders["side"] == "buy")
            & (result.orders["trade_date"] == pd.Timestamp("2026-01-06")),
            "quantity",
        ].iloc[0]
    )
    prior_fifo_sell_quantity = int(
        result.orders.loc[
            (result.orders["symbol"] == "000001.SZ")
            & (result.orders["side"] == "sell")
            & (result.orders["trade_date"] < pd.Timestamp("2026-01-08")),
            "quantity",
        ].sum()
    )
    first_lot_remaining = first_buy_quantity - prior_fifo_sell_quantity
    second_lot_quantity_sold = int(rebalance_trade["quantity"]) - first_lot_remaining
    expected_fifo_entry_price = (
        first_lot_remaining * 10.0 + second_lot_quantity_sold * 20.0
    ) / int(rebalance_trade["quantity"])

    assert rebalance_trade["entry_price"] == pytest.approx(expected_fifo_entry_price)
    assert rebalance_trade["exit_price"] == pytest.approx(20.0)
    assert rebalance_trade["gross_pnl"] == pytest.approx(
        20.0 * int(rebalance_trade["quantity"])
        - (first_lot_remaining * 10.0 + second_lot_quantity_sold * 20.0)
    )


def test_shared_cash_rebalance_does_not_sell_same_day_bought_lot():
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 3 + ["000002.SZ"] * 3,
            "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"] * 2),
            "open": [10.0, 10.0, 10.0, 20.0, 20.0, 20.0],
            "close": [10.0, 10.0, 10.0, 20.0, 20.0, 20.0],
            "rsi_2": [5.0, 20.0, 20.0, 5.0, 20.0, 20.0],
            "signal_score": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=10,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=1,
    )

    result = engine.run(frame, request)

    same_day_sells = result.orders.loc[
        (result.orders["side"] == "sell")
        & (result.orders["reason"] == "rebalance")
        & (result.orders["trade_date"] == pd.Timestamp("2026-01-06"))
    ]
    assert same_day_sells.empty


def test_shared_cash_backtest_reports_failed_rebalance_diagnostics():
    frame = make_shared_frame()
    frame["open"] = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0]
    frame["close"] = frame["open"]
    frame["limit_down"] = False
    frame.loc[
        (frame["ts_code"] == "000002.SZ")
        & (frame["trade_date"] == pd.Timestamp("2026-01-07")),
        "limit_down",
    ] = True
    frame["signal_score"] = [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0]
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=120000.0,
        entry_signal="rsi_2 < 10",
        holding_days=4,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=2,
    )

    result = engine.run(frame, request)
    failed_rebalance = result.failed_orders.loc[result.failed_orders["reason"] == "rebalance"]

    assert failed_rebalance["failure_reason"].tolist() == ["limit_down_sell_blocked"]
    assert result.summary["failed_rebalance_order_count"] == len(failed_rebalance)
    assert result.summary["failed_rebalance_notional"] == pytest.approx(float(failed_rebalance["notional"].sum()))


def test_shared_cash_backtest_exits_by_stop_loss_before_holding_period():
    frame = make_shared_frame()
    frame.loc[2, "low"] = 9.0
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
        max_positions=1,
        stop_loss_pct=0.08,
    )

    result = engine.run(frame, request)

    assert result.trades.iloc[0]["exit_date"] == pd.Timestamp("2026-01-07")
    assert result.trades.iloc[0]["exit_reason"] == "stop_loss"


def test_shared_cash_backtest_exits_by_take_profit_before_holding_period():
    frame = make_shared_frame()
    frame.loc[2, "high"] = 11.5
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
        max_positions=1,
        take_profit_pct=0.10,
    )

    result = engine.run(frame, request)

    assert result.trades.iloc[0]["exit_date"] == pd.Timestamp("2026-01-07")
    assert result.trades.iloc[0]["exit_reason"] == "take_profit"


def test_shared_cash_backtest_exits_by_trailing_stop_before_holding_period():
    frame = make_shared_frame()
    frame.loc[2, "high"] = 12.0
    frame.loc[3, "low"] = 10.7
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=4,
        max_positions=1,
        trailing_stop_pct=0.08,
    )

    result = engine.run(frame, request)

    assert result.trades.iloc[0]["exit_date"] == pd.Timestamp("2026-01-08")
    assert result.trades.iloc[0]["exit_reason"] == "trailing_stop"


def test_shared_cash_backtest_reports_failed_order_diagnostics_total():
    frame = make_shared_frame()
    frame.loc[
        (frame["ts_code"] == "000001.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-06")),
        "open",
    ] = 9999.0
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
    )

    result = engine.run(frame, request)

    assert "failed_order_count" in result.summary
    assert result.summary["failed_order_count"] == len(result.failed_orders)


def test_shared_cash_backtest_reports_failed_order_diagnostics_by_failure_reason():
    frame = make_shared_frame()
    frame.loc[
        (frame["ts_code"] == "000001.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-06")),
        "open",
    ] = 9999.0
    frame.loc[
        (frame["ts_code"] == "000002.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-06")),
        "limit_up",
    ] = True
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
    )

    result = engine.run(frame, request)

    by_failure_reason = result.summary["failed_order_count_by_failure_reason"]
    assert by_failure_reason["limit_up_buy_blocked"] == 1
    assert "failed_order_notional_by_failure_reason" in result.summary
    assert result.summary["failed_order_notional_by_failure_reason"]["limit_up_buy_blocked"] > 0


def test_shared_cash_backtest_reports_failed_order_diagnostics_by_reason():
    frame = make_shared_frame()
    frame["open"] = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0]
    frame["close"] = frame["open"]
    frame["limit_down"] = False
    frame.loc[
        (frame["ts_code"] == "000002.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-07")),
        "limit_down",
    ] = True
    frame["signal_score"] = [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0]
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=120000.0,
        entry_signal="rsi_2 < 10",
        holding_days=4,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=2,
    )

    result = engine.run(frame, request)

    by_reason = result.summary["failed_order_count_by_reason"]
    assert "rebalance" in by_reason
    assert by_reason["rebalance"] >= 1
    assert "failed_order_notional_by_reason" in result.summary
    assert result.summary["failed_order_notional_by_reason"]["rebalance"] > 0


def test_shared_cash_backtest_diagnostics_preserves_failed_rebalance_fields():
    frame = make_shared_frame()
    frame["open"] = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0, 20.0]
    frame["close"] = frame["open"]
    frame["limit_down"] = False
    frame.loc[
        (frame["ts_code"] == "000002.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-07")),
        "limit_down",
    ] = True
    frame["signal_score"] = [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0]
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=120000.0,
        entry_signal="rsi_2 < 10",
        holding_days=4,
        max_positions=2,
        weight_model="score_weight",
        score_column="signal_score",
        rebalance_interval_days=2,
    )

    result = engine.run(frame, request)

    assert "failed_rebalance_order_count" in result.summary
    assert "failed_rebalance_notional" in result.summary
    assert result.summary["failed_rebalance_order_count"] >= 0
    assert result.summary["failed_rebalance_notional"] >= 0


def test_shared_cash_backtest_reports_failed_order_side_diagnostics():
    frame = make_shared_frame()
    frame.loc[
        (frame["ts_code"] == "000001.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-06")),
        "open",
    ] = 9999.0
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
    )

    result = engine.run(frame, request)

    assert "failed_order_count_by_side" in result.summary
    assert "failed_order_notional_by_side" in result.summary
    by_side = result.summary["failed_order_count_by_side"]
    notional_by_side = result.summary["failed_order_notional_by_side"]
    assert isinstance(by_side, dict)
    assert isinstance(notional_by_side, dict)
    assert sum(by_side.values()) == result.summary["failed_order_count"]
    for side_key in by_side:
        assert side_key in notional_by_side
        assert notional_by_side[side_key] > 0


def test_shared_cash_backtest_failed_order_side_diagnostics_empty():
    frame = make_shared_frame()
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
    )

    result = engine.run(frame, request)

    assert "failed_order_count_by_side" in result.summary
    assert "failed_order_notional_by_side" in result.summary
    if result.summary["failed_order_count"] == 0:
        assert result.summary["failed_order_count_by_side"] == {}
        assert result.summary["failed_order_notional_by_side"] == {}


def test_shared_cash_backtest_empty_result_includes_side_diagnostics():
    frame = make_shared_frame().iloc[0:0].copy()
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
    )

    result = engine.run(frame, request)

    assert result.summary["failed_order_count_by_side"] == {}
    assert result.summary["failed_order_notional_by_side"] == {}


def test_shared_cash_metadata_columns_in_orders_when_requested():
    frame = make_shared_frame().copy()
    frame["sector"] = ["Finance"] * 5 + ["RealEstate"] * 5
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["sector"],
    )

    result = engine.run(frame, request)

    assert "sector" in result.orders.columns
    assert result.orders.loc[result.orders["symbol"] == "000001.SZ", "sector"].iloc[0] == "Finance"
    assert result.orders.loc[result.orders["symbol"] == "000002.SZ", "sector"].iloc[0] == "RealEstate"


def test_shared_cash_metadata_columns_in_trades_when_requested():
    frame = make_shared_frame().copy()
    frame["industry"] = ["Bank"] * 5 + ["Property"] * 5
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["industry"],
    )

    result = engine.run(frame, request)

    assert "industry" in result.trades.columns
    assert result.trades.loc[result.trades["symbol"] == "000001.SZ", "industry"].iloc[0] == "Bank"
    assert result.trades.loc[result.trades["symbol"] == "000002.SZ", "industry"].iloc[0] == "Property"


def test_shared_cash_metadata_columns_in_failed_orders_when_requested():
    frame = make_shared_frame().copy()
    frame["sector"] = ["Finance"] * 5 + ["RealEstate"] * 5
    frame.loc[
        (frame["ts_code"] == "000001.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-06")),
        "limit_up",
    ] = True
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["sector"],
    )

    result = engine.run(frame, request)

    assert len(result.failed_orders) > 0
    assert "sector" in result.failed_orders.columns
    assert result.failed_orders.loc[result.failed_orders["symbol"] == "000001.SZ", "sector"].iloc[0] == "Finance"


def test_shared_cash_metadata_skips_missing_requested_columns():
    frame = make_shared_frame()
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["nonexistent_column"],
    )

    result = engine.run(frame, request)

    assert "nonexistent_column" not in result.orders.columns
    assert "nonexistent_column" not in result.trades.columns


def test_shared_cash_default_output_unchanged_when_no_metadata_requested():
    frame = make_shared_frame()
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
    )

    result = engine.run(frame, request)

    orders_default_cols = {"symbol", "trade_date", "side", "quantity", "price", "notional", "cost", "reason"}
    trades_default_cols = {"symbol", "entry_date", "exit_date", "quantity", "entry_price", "exit_price", "gross_pnl", "cost", "net_pnl", "exit_reason"}
    assert set(result.orders.columns) == orders_default_cols
    assert set(result.trades.columns) == trades_default_cols


def test_shared_cash_empty_metadata_columns_list_is_noop():
    frame = make_shared_frame()
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=[],
    )

    result = engine.run(frame, request)

    orders_default_cols = {"symbol", "trade_date", "side", "quantity", "price", "notional", "cost", "reason"}
    assert set(result.orders.columns) == orders_default_cols


def test_shared_cash_metadata_collision_does_not_overwrite_order_trade_date():
    frame = make_shared_frame().copy()
    frame["trade_date"] = frame["trade_date"]  # col name collides with row field
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["trade_date"],
    )

    result = engine.run(frame, request)

    sell_orders = result.orders.loc[result.orders["side"] == "sell"]
    assert not sell_orders.empty
    for _, order in sell_orders.iterrows():
        assert order["trade_date"] != pd.Timestamp("2026-01-05")


def test_shared_cash_metadata_collision_does_not_overwrite_trade_exit_reason():
    frame = make_shared_frame().copy()
    frame["exit_reason"] = ["misc"] * 5 + ["misc"] * 5
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["exit_reason"],
    )

    result = engine.run(frame, request)

    assert not result.trades.empty
    for _, trade in result.trades.iterrows():
        assert trade["exit_reason"] == "holding_period"


def test_shared_cash_metadata_collision_does_not_overwrite_failed_order_failure_reason():
    frame = make_shared_frame().copy()
    frame["failure_reason"] = ["custom"] * 5 + ["custom"] * 5
    frame.loc[
        (frame["ts_code"] == "000001.SZ") & (frame["trade_date"] == pd.Timestamp("2026-01-06")),
        "limit_up",
    ] = True
    engine = SharedCashBacktestEngine(AShareMarketProfile())
    request = SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["failure_reason"],
    )

    result = engine.run(frame, request)

    assert not result.failed_orders.empty
    for _, fo in result.failed_orders.iterrows():
        assert fo["failure_reason"] == "limit_up_buy_blocked"
