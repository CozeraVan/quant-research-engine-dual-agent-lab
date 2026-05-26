import pandas as pd
import pytest

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest


def make_batch_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 6 + ["000002.SZ"] * 6,
            "trade_date": pd.to_datetime(
                [
                    "2026-01-05",
                    "2026-01-06",
                    "2026-01-07",
                    "2026-01-08",
                    "2026-01-09",
                    "2026-01-12",
                ]
                * 2
            ),
            "open": [10.0, 10.2, 10.5, 10.8, 11.0, 11.2, 20.0, 19.8, 19.5, 19.0, 18.8, 18.6],
            "close": [10.1, 10.4, 10.7, 10.9, 11.1, 11.3, 19.9, 19.7, 19.3, 18.9, 18.7, 18.5],
            "rsi_2": [5.0, 20.0, 30.0, 40.0, 50.0, 60.0, 5.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "board": ["main_board"] * 6 + ["chinext"] * 6,
            "is_st": [False] * 12,
        }
    )


def test_batch_backtest_runs_one_single_symbol_backtest_per_symbol():
    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_batch_frame(), request)

    assert set(result.results) == {"000001.SZ", "000002.SZ"}
    assert result.summary["symbol"].tolist() == ["000001.SZ", "000002.SZ"]
    assert result.summary["trade_count"].tolist() == [1, 1]
    assert result.summary["order_count"].tolist() == [2, 2]
    assert result.summary["failed_order_count"].tolist() == [0, 0]
    assert result.summary["board"].tolist() == ["main_board", "chinext"]
    assert result.summary["is_st"].tolist() == [False, False]
    assert result.summary.loc[0, "total_return"] == pytest.approx(0.077216944)
    assert result.summary.loc[1, "total_return"] < 0


def test_batch_backtest_can_infer_symbols_from_frame():
    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=None,
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_batch_frame(), request)

    assert result.symbols == ["000001.SZ", "000002.SZ"]


def test_batch_backtest_rejects_invalid_initial_cash():
    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ"],
        initial_cash_per_symbol=0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    with pytest.raises(ValueError, match="initial_cash_per_symbol must be positive"):
        engine.run(make_batch_frame(), request)


def test_batch_backtest_includes_default_metadata_columns_in_summary():
    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(make_batch_frame(), request)

    assert "board" in result.summary.columns
    assert "is_st" in result.summary.columns


def test_batch_backtest_includes_extra_metadata_columns_when_requested():
    frame = make_batch_frame()
    frame["sector"] = ["Finance"] * 6 + ["Tech"] * 6

    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
        summary_metadata_columns=["sector"],
    )

    result = engine.run(frame, request)

    assert "sector" in result.summary.columns
    assert result.summary.loc[0, "sector"] == "Finance"
    assert result.summary.loc[1, "sector"] == "Tech"
    # Default fixed metadata columns still present
    assert "board" in result.summary.columns


def test_batch_backtest_extra_metadata_column_absent_from_frame_is_skipped():
    frame = make_batch_frame()

    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
        summary_metadata_columns=["sector"],
    )

    result = engine.run(frame, request)

    # sector is not in the frame, so it should not appear in summary
    assert "sector" not in result.summary.columns


def test_batch_backtest_default_metadata_columns_not_duplicated():
    frame = make_batch_frame()
    # board is already in SUMMARY_METADATA_COLUMNS
    frame["board"] = ["main_board"] * 6 + ["chinext"] * 6

    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
        summary_metadata_columns=["board"],
    )

    result = engine.run(frame, request)

    assert "board" in result.summary.columns


def test_batch_backtest_includes_industry_group_in_metadata():
    frame = make_batch_frame()
    frame["industry"] = ["Finance"] * 6 + ["Tech"] * 6
    frame["industry_group"] = ["finance"] * 6 + ["technology"] * 6

    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)

    assert "industry" in result.summary.columns
    assert "industry_group" in result.summary.columns
    assert result.summary.loc[0, "industry"] == "Finance"
    assert result.summary.loc[0, "industry_group"] == "finance"
    assert result.summary.loc[1, "industry"] == "Tech"
    assert result.summary.loc[1, "industry_group"] == "technology"


def test_batch_backtest_summary_includes_buy_hold_fields():
    frame = make_batch_frame()

    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)

    # buy-and-hold fields flow through from single-symbol summary
    assert "buy_hold_return" in result.summary.columns
    assert "excess_return_vs_buy_hold" in result.summary.columns
    # 000001.SZ: first open=10.0, last close=11.3 → 0.13
    assert result.summary.loc[0, "buy_hold_return"] == pytest.approx(0.13)
    # 000002.SZ: first open=20.0, last close=18.5 → -0.075
    assert result.summary.loc[1, "buy_hold_return"] == pytest.approx(-0.075)


def test_batch_backtest_summary_metrics_includes_buy_hold_aggregates():
    frame = make_batch_frame()

    engine = BatchBacktestEngine(AShareMarketProfile())
    request = BatchBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )

    result = engine.run(frame, request)
    metrics = result.summary_metrics

    # buy-and-hold aggregates are present
    assert "buy_hold_return" in metrics
    assert "mean_buy_hold_return" in metrics
    assert "median_buy_hold_return" in metrics
    assert "mean_excess_return_vs_buy_hold" in metrics
    assert "median_excess_return_vs_buy_hold" in metrics
    # mean of (0.13, -0.075) = 0.0275
    assert metrics["mean_buy_hold_return"] == pytest.approx(0.0275)
    # median of (0.13, -0.075) = 0.0275
    assert metrics["median_buy_hold_return"] == pytest.approx(0.0275)
