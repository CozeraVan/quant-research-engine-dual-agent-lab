from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd

from quant_research_engine.game.data import PostgresGameDataProvider, bars_from_rows
from quant_research_engine.game.factors import DEFAULT_CANONICALS

START = date(2020, 1, 1)
CLOSE_EMA5 = DEFAULT_CANONICALS[0]
TYPICAL_EMA5 = "factors.stock_daily_overlap_typical_price.ema_5"


def test_raw_rows_are_qfq_anchored():
    rows = [
        {"trade_date": START, "open": 10, "high": 12, "low": 9, "close": 11,
         "pre_close": 10, "vol": 100, "amount": 1000, "adj_factor": 2},
        {"trade_date": START + timedelta(days=1), "open": 20, "high": 22, "low": 19,
         "close": 21, "pre_close": 11, "vol": 200, "amount": 2000, "adj_factor": 4},
    ]
    bars = bars_from_rows(rows)
    assert bars[0].close == 5.5 and bars[0].open == 5.0 and bars[1].close == 21.0


class FakeStore:
    settings = SimpleNamespace(tables=SimpleNamespace(market_daily_table="public.stock_daily"))

    def __init__(self, empty=False):
        self.calls = []
        self.empty = empty

    def qualified_table(self, name):
        return name

    def latest_trade_date(self):
        return START + timedelta(days=1499)

    def list_symbols_with_bars(self, start, end):
        return ["600000.SH"]

    def load_raw_bars(self, symbol, start, end):
        return [{"trade_date": START + timedelta(days=i), "open": 10, "high": 11,
                 "low": 9, "close": 10, "pre_close": 10, "vol": 100,
                 "amount": 1000, "adj_factor": 1} for i in range(1500)]

    def load_factor_history(self, symbols, requests, start, end):
        canonicals = [request.logical_name for request in requests]
        self.calls.append(canonicals)
        if self.empty:
            return pd.DataFrame()
        data = {"ts_code": ["600000.SH"] * 1500,
                "trade_date": [pd.Timestamp(START) + pd.Timedelta(days=i) for i in range(1500)]}
        for canonical in canonicals:
            data[canonical] = [10.0 if canonical == CLOSE_EMA5 else 20.0] * 1500
        return pd.DataFrame(data)


def test_default_and_same_column_variants_are_canonical_cached():
    store = FakeStore()
    provider = PostgresGameDataProvider(store)
    game = provider.create_session(seed=2026)
    assert len(store.calls) == 1
    assert set(store.calls[0]) == set(DEFAULT_CANONICALS)
    assert game.public_history()[-1]["factors"][CLOSE_EMA5] == 10.0

    provider.load_selected(game, [CLOSE_EMA5, TYPICAL_EMA5])
    assert store.calls[-1] == [TYPICAL_EMA5]
    values = game.public_history()[-1]["factors"]
    assert values[CLOSE_EMA5] == 10.0 and values[TYPICAL_EMA5] == 20.0
    assert game.loaded_canonicals == {*DEFAULT_CANONICALS, TYPICAL_EMA5}

    provider.load_selected(game, [CLOSE_EMA5, TYPICAL_EMA5])
    assert len(store.calls) == 2


def test_empty_factor_response_does_not_repeat_requests():
    store = FakeStore(empty=True)
    provider = PostgresGameDataProvider(store)
    game = provider.create_session(seed=2026)
    calls = len(store.calls)
    provider.load_selected(game, [CLOSE_EMA5])
    assert len(store.calls) == calls
    assert CLOSE_EMA5 in game.loaded_canonicals
