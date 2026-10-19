"""成交价列参数（entry_price_column / exit_price_column）引擎层测试。

覆盖：vwap 成交价正确性、exit_price_column 独立性（入场 open / 出场 close）、
默认不变性（不显式给出场价列时卖出跟随入场价列，与既有行为逐字节一致）、
simulator ↔ vectorized 等值、batch / shared 路径透传。
"""

import pandas as pd
import pytest

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest
from quant_research_engine.portfolio.single_symbol import (
    SingleSymbolBacktestEngine,
    SingleSymbolBacktestRequest,
)
from quant_research_engine.portfolio.single_symbol_vectorized import SingleSymbolVectorizedEngine

PROFILE = AShareMarketProfile()  # 默认滑点 0：成交价 == 行情列原值


def make_price_frame(symbol: str = "000001.SZ", n: int = 6) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": [symbol] * n,
            "trade_date": pd.to_datetime(
                ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"][:n]
            ),
            "open": [10.0, 10.2, 10.5, 10.8, 11.0, 11.2][:n],
            "close": [10.1, 10.4, 10.7, 10.9, 11.1, 11.3][:n],
            "vwap": [10.05, 10.3, 10.6, 10.85, 11.05, 11.25][:n],
            "rsi_2": [5.0, 20.0, 30.0, 40.0, 50.0, 60.0][:n],
        }
    )


def make_single_request(**overrides) -> SingleSymbolBacktestRequest:
    defaults = {
        "symbol": "000001.SZ",
        "initial_cash": 100000.0,
        "entry_signal": "rsi_2 < 10",
        "holding_days": 3,
    }
    defaults.update(overrides)
    return SingleSymbolBacktestRequest(**defaults)


# 信号 bar0（rsi=5）→ bar1 买入；holding_days=3 → bar4 卖出
BUY_BAR, SELL_BAR = 1, 4


def test_entry_price_column_vwap_fills_at_vwap():
    frame = make_price_frame()
    result = SingleSymbolBacktestEngine(PROFILE).run(
        frame, make_single_request(entry_price_column="vwap")
    )
    buy = result.orders.loc[result.orders["side"] == "buy"].iloc[0]
    assert buy["price"] == pytest.approx(frame["vwap"].iloc[BUY_BAR])


def test_exit_price_column_independent_from_entry():
    """入场 open / 出场 close：卖价取 close 列，不受入场价列影响。"""
    frame = make_price_frame()
    result = SingleSymbolBacktestEngine(PROFILE).run(
        frame, make_single_request(entry_price_column="open", exit_price_column="close")
    )
    sell = result.orders.loc[result.orders["side"] == "sell"].iloc[0]
    assert sell["price"] == pytest.approx(frame["close"].iloc[SELL_BAR])
    assert result.trades.iloc[0]["entry_price"] == pytest.approx(frame["open"].iloc[BUY_BAR])
    assert result.trades.iloc[0]["exit_price"] == pytest.approx(frame["close"].iloc[SELL_BAR])


def test_exit_price_column_default_follows_entry():
    """不显式给 exit_price_column：卖出沿用入场价列（既有行为不变）。"""
    frame = make_price_frame()
    default_result = SingleSymbolBacktestEngine(PROFILE).run(frame, make_single_request())
    explicit_result = SingleSymbolBacktestEngine(PROFILE).run(
        frame, make_single_request(exit_price_column=None)
    )
    sell = default_result.orders.loc[default_result.orders["side"] == "sell"].iloc[0]
    assert sell["price"] == pytest.approx(frame["open"].iloc[SELL_BAR])
    pd.testing.assert_frame_equal(default_result.orders, explicit_result.orders)
    pd.testing.assert_frame_equal(default_result.trades, explicit_result.trades)
    assert default_result.summary == explicit_result.summary


@pytest.mark.parametrize(
    "entry_col,exit_col",
    [("open", None), ("close", "close"), ("vwap", "vwap"), ("open", "close"), ("vwap", "open")],
)
def test_vectorized_matches_simulator_with_price_columns(entry_col, exit_col):
    frame = make_price_frame()
    request = make_single_request(entry_price_column=entry_col, exit_price_column=exit_col)
    sim = SingleSymbolBacktestEngine(PROFILE).run(frame, request)
    vec = SingleSymbolVectorizedEngine(PROFILE).run(frame, request)
    pd.testing.assert_frame_equal(sim.orders, vec.orders, check_dtype=True)
    pd.testing.assert_frame_equal(sim.trades, vec.trades, check_dtype=True)
    pd.testing.assert_frame_equal(sim.equity_curve, vec.equity_curve, check_dtype=True)
    assert sim.summary == vec.summary


def make_two_symbol_frame() -> pd.DataFrame:
    one = make_price_frame("000001.SZ")
    two = make_price_frame("000002.SZ")
    two["open"] += 10.0
    two["close"] += 10.0
    two["vwap"] += 10.0
    return pd.concat([one, two], ignore_index=True)


@pytest.mark.parametrize("engine_impl", ["simulator", "vectorized"])
def test_batch_passthrough_entry_exit_price_columns(engine_impl):
    frame = make_two_symbol_frame()
    result = BatchBacktestEngine(PROFILE).run(
        frame,
        BatchBacktestRequest(
            symbols=["000001.SZ", "000002.SZ"],
            initial_cash_per_symbol=100000.0,
            entry_signal="rsi_2 < 10",
            holding_days=3,
            entry_price_column="vwap",
            exit_price_column="close",
            engine_impl=engine_impl,
        ),
    )
    for symbol, single in result.results.items():
        buy = single.orders.loc[single.orders["side"] == "buy"].iloc[0]
        sell = single.orders.loc[single.orders["side"] == "sell"].iloc[0]
        expected_buy = frame.loc[frame["ts_code"] == symbol, "vwap"].iloc[BUY_BAR]
        expected_sell = frame.loc[frame["ts_code"] == symbol, "close"].iloc[SELL_BAR]
        assert buy["price"] == pytest.approx(expected_buy)
        assert sell["price"] == pytest.approx(expected_sell)


def test_shared_exit_price_column_independent():
    frame = make_two_symbol_frame()
    result = SharedCashBacktestEngine(PROFILE).run(
        frame,
        SharedCashBacktestRequest(
            symbols=["000001.SZ", "000002.SZ"],
            initial_cash=200000.0,
            entry_signal="rsi_2 < 10",
            holding_days=3,
            max_positions=2,
            entry_price_column="open",
            exit_price_column="close",
        ),
    )
    sells = result.orders.loc[result.orders["side"] == "sell"]
    assert len(sells) == 2
    for _, sell in sells.iterrows():
        expected = frame.loc[frame["ts_code"] == sell["symbol"], "close"].iloc[SELL_BAR]
        assert sell["price"] == pytest.approx(expected)


def test_shared_default_exit_follows_entry():
    frame = make_two_symbol_frame()
    default_result = SharedCashBacktestEngine(PROFILE).run(
        frame,
        SharedCashBacktestRequest(
            symbols=["000001.SZ", "000002.SZ"],
            initial_cash=200000.0,
            entry_signal="rsi_2 < 10",
            holding_days=3,
            max_positions=2,
        ),
    )
    sells = default_result.orders.loc[default_result.orders["side"] == "sell"]
    for _, sell in sells.iterrows():
        expected = frame.loc[frame["ts_code"] == sell["symbol"], "open"].iloc[SELL_BAR]
        assert sell["price"] == pytest.approx(expected)


def test_load_daily_bars_raw_mode_scales_vwap_with_adj_factor(monkeypatch):
    """hfq 口径（QRE_PRICE_BASIS=raw）：vwap 与 OHLC 同乘 adj_factor，保持同尺度。"""
    from quant_research_engine.data.postgres import PostgresDataStore
    from quant_research_engine.data.settings import DatabaseSettings

    settings = DatabaseSettings(market_db_url="postgresql://unused", price_basis="raw")
    store = PostgresDataStore.__new__(PostgresDataStore)
    store.settings = settings
    store.market_engine = None  # _load_table_frame 已打桩，engine 不会被使用

    source = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": pd.to_datetime(["2026-01-05"]),
            "open": [10.0],
            "close": [10.1],
            "vwap": [10.05],
            "vol": [1000.0],
            "amount": [10050.0],
            "adj_factor": [2.0],
        }
    )
    captured = {}

    def fake_load_table_frame(*, engine, table_name, source_columns, start, end, ts_codes, limit):
        captured["source_columns"] = source_columns
        return source.copy()

    monkeypatch.setattr(store, "_load_table_frame", fake_load_table_frame)
    frame = store.load_daily_bars(
        ["000001.SZ"], start=pd.Timestamp("2026-01-01").date(), end=pd.Timestamp("2026-02-01").date(),
        fields=["open", "close", "vwap", "vol", "amount"],
    )
    assert "adj_factor" in captured["source_columns"]  # raw 模式自动补读复权因子
    assert frame.iloc[0]["vwap"] == pytest.approx(20.1)  # 10.05 × 2.0，与价格列同尺度
    assert frame.iloc[0]["close"] == pytest.approx(20.2)
    assert frame.iloc[0]["vol"] == pytest.approx(1000.0)  # 量额不缩放
    assert "adj_factor" not in frame.columns
