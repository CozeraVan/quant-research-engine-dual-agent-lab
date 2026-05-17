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
