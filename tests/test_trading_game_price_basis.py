"""价格口径回归：因子表按 hfq 存储时必须按会话锚点换算回前复权尺度。"""

from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_research_engine.game.data import PostgresGameDataProvider, bars_from_rows, qfq_anchor
from quant_research_engine.game.factors import (
    DEFAULT_CANONICALS, is_price_scaled, price_scaled_canonicals,
)
from quant_research_engine.game.validation import (
    audit_price_factors, recompute_boll, recompute_ema,
)

START = date(2020, 1, 1)
N = 1500
ADJ = 4.0
EMA5, EMA20, EMA60, EMA250 = DEFAULT_CANONICALS[:4]
MACD = DEFAULT_CANONICALS[4]
MACDS = DEFAULT_CANONICALS[5]
MACDH = DEFAULT_CANONICALS[6]
RSI14 = DEFAULT_CANONICALS[7]
BBL, BBM, BBU = DEFAULT_CANONICALS[8:11]
BB_WIDTH = "factors.stock_daily_volatility_close.bb_width_20_2_0"
PSARL = "factors.stock_daily_trend_close.psarl_0_02_0_2"
PSARAF = "factors.stock_daily_trend_close.psaraf_0_02_0_2"
EXTRA = (BB_WIDTH, PSARL, PSARAF)


def qfq_closes():
    return [10.0 + 0.05 * i + 0.8 * ((i % 7) - 3) for i in range(N)]


def qfq_factor_series(closes):
    """按前复权尺度独立重算价格型因子，与游戏校验保持同一公式。"""
    ema12 = recompute_ema(closes, 12)
    ema26 = recompute_ema(closes, 26)
    macd = [None if a is None or b is None else a - b for a, b in zip(ema12, ema26)]
    macd_clean = [value if value is not None else 0.0 for value in macd]
    boll = recompute_boll(closes, 20, 2.0, ddof=1)
    series = {
        EMA5: recompute_ema(closes, 5), EMA20: recompute_ema(closes, 20),
        EMA60: recompute_ema(closes, 60), EMA250: recompute_ema(closes, 250),
        MACD: macd, MACDS: recompute_ema(macd_clean, 9),
        MACDH: [None if a is None or b is None else a - b
                for a, b in zip(macd, recompute_ema(macd_clean, 9))],
        BBL: boll["bbl"], BBM: boll["bbm"], BBU: boll["bbu"],
    }
    return series


def hfq_value(canonical, index, series, closes):
    if canonical == RSI14:
        return 55.0
    if canonical == BB_WIDTH:
        return 0.09
    if canonical == PSARAF:
        return 0.05
    if canonical == PSARL:
        return closes[index] * 0.95 * ADJ
    value = series[canonical][index]
    return None if value is None else value * ADJ


class FakeStore:
    settings = SimpleNamespace(tables=SimpleNamespace(market_daily_table="public.stock_daily"))

    def __init__(self, *, skip_scale=False, raise_on_load=False):
        self.calls = []
        self.skip_scale = skip_scale
        self.raise_on_load = raise_on_load
        self.closes = qfq_closes()
        self.series = qfq_factor_series(self.closes)

    def qualified_table(self, name):
        return name

    def latest_trade_date(self):
        return START + timedelta(days=N - 1)

    def list_symbols_with_bars(self, start, end):
        return ["600000.SH"]

    def load_raw_bars(self, symbol, start, end):
        return [{"trade_date": START + timedelta(days=i),
                 "open": c, "high": c + 1, "low": c - 1, "close": c, "pre_close": c,
                 "vol": 100, "amount": 1000, "adj_factor": ADJ}
                for i, c in enumerate(self.closes)]

    def load_factor_history(self, symbols, requests, start, end):
        if self.raise_on_load:
            raise PermissionError("factor table unavailable")
        canonicals = [request.logical_name for request in requests]
        self.calls.append(canonicals)
        data = {"ts_code": ["600000.SH"] * N,
                "trade_date": [pd.Timestamp(START) + pd.Timedelta(days=i) for i in range(N)]}
        for canonical in canonicals:
            values = []
            for index in range(N):
                value = hfq_value(canonical, index, self.series, self.closes)
                if value is not None and self.skip_scale:
                    value = value / ADJ
                values.append(value)
            data[canonical] = values
        return pd.DataFrame(data)


def close_enough(actual, expected):
    assert actual is not None and expected is not None
    assert abs(actual - expected) <= max(0.02, abs(expected) * 2e-3)


def test_bars_and_anchor_share_one_qfq_basis():
    rows = FakeStore().load_raw_bars("600000.SH", START, START)
    bars = bars_from_rows(rows)
    assert qfq_anchor(rows) == ADJ
    assert rows[0]["close"] == qfq_closes()[0]
    assert bars[0].close == pytest.approx(qfq_closes()[0])


def test_price_factors_are_converted_to_qfq_and_plain_factors_kept():
    store = FakeStore()
    provider = PostgresGameDataProvider(store, candidate_limit=1)
    game = provider.create_session(seed=2026)
    provider.load_selected(game, [*DEFAULT_CANONICALS, *EXTRA])

    assert game.price_anchor == ADJ
    last = game.factors[N - 1]
    for canonical in (EMA5, EMA20, EMA60, EMA250, BBL, BBM, BBU):
        close_enough(last[canonical], store.series[canonical][N - 1])
    close_enough(last[PSARL], store.closes[N - 1] * 0.95)
    assert last[RSI14] == pytest.approx(55.0)
    assert last[BB_WIDTH] == pytest.approx(0.09)
    assert last[PSARAF] == pytest.approx(0.05)

    audit = game.factor_audit
    assert audit["checked"] > 0
    assert audit["mismatches"] == 0
    assert audit["max_abs_diff"] <= 0.02
    assert set(audit["canonicals"]) >= {EMA5, BBM, BBU}


def test_audit_flags_unconverted_price_factors():
    store = FakeStore(skip_scale=True)
    provider = PostgresGameDataProvider(store, candidate_limit=1)
    game = provider.create_session(seed=2026)

    assert game.factor_audit["mismatches"] > 0
    assert game.factor_audit["max_abs_diff"] > 0.02


def test_audit_against_game_bars_detects_mismatch_directly():
    closes = qfq_closes()
    bars = [SimpleNamespace(close=value) for value in closes]
    expected = recompute_ema(closes, 5)
    factors = {index: {EMA5: value} for index, value in enumerate(expected) if value is not None}
    clean = audit_price_factors(bars, factors, [EMA5])
    assert clean["mismatches"] == 0

    shifted = {index: {EMA5: value * 1.3} for index, value in enumerate(expected) if value is not None}
    dirty = audit_price_factors(bars, shifted, [EMA5])
    assert dirty["mismatches"] == len(shifted)


def test_family_classification_matches_evidence():
    assert is_price_scaled("ema", "ema_5")
    assert is_price_scaled("bbl", "bbl_20_2_0_2_0")
    assert is_price_scaled("macd", "macd_12_26_9")
    assert is_price_scaled("psar", "psarl_0_02_0_2")
    assert not is_price_scaled("psar", "psaraf_0_02_0_2")
    assert is_price_scaled("zigzag") is False
    assert not is_price_scaled("rsi", "rsi_14")
    assert not is_price_scaled("bbb", "bbb_20_2_0_2_0")
    assert not is_price_scaled("bb_width", "bb_width_20_2_0")
    assert not is_price_scaled("unknown_family", "unknown_1")
    assert price_scaled_canonicals([EMA5, RSI14, PSARL, PSARAF]) == {
        EMA5: True, RSI14: False, PSARL: True, PSARAF: False,
    }


def test_factor_load_failure_degrades_without_raising():
    store = FakeStore(raise_on_load=True)
    provider = PostgresGameDataProvider(store, candidate_limit=1)
    game = provider.create_session(seed=2026)

    assert game.factor_errors
    assert set(game.factor_errors) == set(DEFAULT_CANONICALS)
    assert game.factor_audit["checked"] == 0
    assert game.factors == {}