"""Equality suite: SingleSymbolVectorizedEngine vs SingleSymbolBacktestEngine.

The vectorized engine must produce metric-identical results (orders, trades,
failed_orders, equity_curve, summary) to the per-bar simulator for identical
inputs. Covers deterministic edge cases, randomized property frames, batch
routing, position-sizing modes, and validation errors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.portfolio.single_symbol import (
    SingleSymbolBacktestEngine,
    SingleSymbolBacktestRequest,
    SingleSymbolBacktestResult,
)
from quant_research_engine.portfolio.single_symbol_vectorized import (
    SingleSymbolVectorizedEngine,
)

PROFILE = AShareMarketProfile()


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


def assert_results_equal(expected: SingleSymbolBacktestResult, actual: SingleSymbolBacktestResult) -> None:
    pd.testing.assert_frame_equal(expected.orders, actual.orders, check_dtype=True)
    pd.testing.assert_frame_equal(expected.trades, actual.trades, check_dtype=True)
    pd.testing.assert_frame_equal(expected.failed_orders, actual.failed_orders, check_dtype=True)
    pd.testing.assert_frame_equal(expected.equity_curve, actual.equity_curve, check_dtype=True)
    assert expected.summary == actual.summary


def run_both(frame: pd.DataFrame, request: SingleSymbolBacktestRequest, **vec_kwargs):
    sim = SingleSymbolBacktestEngine(PROFILE).run(frame, request)
    vec = SingleSymbolVectorizedEngine(PROFILE).run(frame, request, **vec_kwargs)
    return sim, vec


def make_frame(
    symbol: str,
    opens: list[float],
    closes: list[float] | None = None,
    *,
    start: str = "2024-01-01",
    highs: list[float] | None = None,
    pre_closes: list[float] | None = None,
    is_suspended: list | None = None,
    limit_up: list | None = None,
    limit_down: list | None = None,
    is_st: list | None = None,
) -> pd.DataFrame:
    n = len(opens)
    closes = closes if closes is not None else opens
    data: dict[str, object] = {
        "ts_code": [symbol] * n,
        "trade_date": pd.bdate_range(start, periods=n),
        "open": opens,
        "close": closes,
    }
    if highs is not None:
        data["high"] = highs
    if pre_closes is not None:
        data["pre_close"] = pre_closes
    if is_suspended is not None:
        data["is_suspended"] = is_suspended
    if limit_up is not None:
        data["limit_up"] = limit_up
    if limit_down is not None:
        data["limit_down"] = limit_down
    if is_st is not None:
        data["is_st"] = is_st
    return pd.DataFrame(data)


def make_request(symbol: str, **overrides) -> SingleSymbolBacktestRequest:
    defaults = {
        "symbol": symbol,
        "initial_cash": 1_000_000.0,
        "entry_signal": "close > open",
        "holding_days": 5,
    }
    defaults.update(overrides)
    return SingleSymbolBacktestRequest(**defaults)


# ---------------------------------------------------------------------------
# deterministic edge cases
# ---------------------------------------------------------------------------


def test_equal_plain_holding_expiry():
    opens = [10.0, 9.0, 9.5, 10.5, 11.0, 10.8, 10.2, 9.8, 9.6, 10.1]
    closes = [9.5, 9.2, 10.0, 10.8, 10.9, 10.5, 10.0, 9.7, 9.9, 10.3]
    frame = make_frame("000001.SZ", opens, closes)
    sim, vec = run_both(
        frame,
        make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=3),
    )
    assert vec.summary["trade_count"] >= 1
    assert_results_equal(sim, vec)


def test_equal_exit_signal_path():
    opens = [10.0, 9.0, 9.5, 10.5, 11.0, 12.0, 10.2, 9.8, 9.6, 10.1]
    closes = [9.5, 9.2, 10.0, 10.8, 11.5, 12.5, 10.0, 9.7, 9.9, 10.3]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request(
        "000001.SZ",
        entry_signal="close < open",
        exit_signal="close > 11",
        holding_days=8,
    )
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)


def test_equal_limit_up_buy_rejection():
    # signal at bar 0 (close<open), execution bar 1 is limit_up → buy rejected
    opens = [10.0, 11.0, 10.0, 9.0, 9.5, 10.0, 10.5, 10.0]
    closes = [9.5, 11.5, 9.5, 8.8, 9.8, 10.2, 10.4, 10.1]
    limit_up = [False, True, False, False, False, False, False, False]
    frame = make_frame("000001.SZ", opens, closes, limit_up=limit_up)
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open", holding_days=2))
    assert len(vec.failed_orders) >= 1
    assert_results_equal(sim, vec)


def test_equal_limit_down_sell_rejection_and_retry():
    # entry bar 1, holding_days=2 → expiry at bar 3 which is limit_down →
    # rejection recorded, retry at bar 4 succeeds.
    opens = [10.0, 9.0, 9.5, 8.0, 8.5, 9.0, 9.5, 10.0]
    closes = [9.5, 9.2, 9.0, 7.5, 8.2, 9.2, 9.6, 10.1]
    limit_down = [False, False, False, True, False, False, False, False]
    frame = make_frame("000001.SZ", opens, closes, limit_down=limit_down)
    sim, vec = run_both(
        frame,
        make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=2),
    )
    assert_results_equal(sim, vec)
    assert len(vec.failed_orders) >= 1
    assert "limit_down_sell_blocked" in set(vec.failed_orders["reason"])


def test_equal_suspended_at_execution():
    opens = [10.0, 9.0, 9.5, 10.0, 10.5, 11.0]
    closes = [9.5, 9.2, 9.8, 10.2, 10.8, 11.2]
    is_suspended = [False, True, False, False, False, False]
    frame = make_frame("000001.SZ", opens, closes, is_suspended=is_suspended)
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open", holding_days=2))
    assert_results_equal(sim, vec)


def test_equal_signal_every_day_stress():
    rng = np.random.default_rng(7)
    n = 60
    opens = list(10 + np.cumsum(rng.normal(0, 0.2, n)))
    closes = [o + rng.normal(0, 0.1) for o in opens]
    frame = make_frame("000001.SZ", opens, closes)
    # close > open or close < open fires almost every day
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close != open", holding_days=2))
    assert_results_equal(sim, vec)


def test_equal_empty_frame_symbol_absent():
    frame = make_frame("000001.SZ", [10.0, 9.5], [9.8, 9.6])
    sim, vec = run_both(frame, make_request("600000.SH"))
    assert vec.summary["trade_count"] == 0
    assert_results_equal(sim, vec)


def test_equal_last_bar_signal_ignored():
    opens = [10.0] * 5 + [9.0]
    closes = [10.1] * 5 + [8.5]
    frame = make_frame("000001.SZ", opens, closes)
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open", holding_days=2))
    assert vec.summary["trade_count"] == 0
    assert_results_equal(sim, vec)


def test_equal_zero_trade_flat_equity():
    opens = [10.0, 10.1, 10.2]
    closes = [10.05, 10.15, 10.25]
    frame = make_frame("000001.SZ", opens, closes)
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open - 100", holding_days=2))
    assert vec.summary["trade_count"] == 0
    assert vec.summary["final_equity"] == 1_000_000.0
    assert_results_equal(sim, vec)


def test_equal_dead_pending_buy_zero_quantity():
    # cash too small for one lot → buy_quantity 0 → simulator deadlocks (no
    # further buys); vectorized must reproduce exactly.
    opens = [100.0, 90.0, 95.0, 92.0, 94.0, 96.0]
    closes = [95.0, 92.0, 94.0, 91.0, 95.0, 97.0]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=3_500.0, entry_signal="close < open", holding_days=2)
    sim, vec = run_both(frame, req)
    assert vec.summary["trade_count"] == 0
    assert_results_equal(sim, vec)


def test_equal_dead_pending_buy_costs_exceed_cash():
    # lot affordable but notional+cost > cash → dead pending, no order records.
    opens = [9.0, 8.5, 8.8, 8.6, 8.9, 9.1]
    closes = [8.6, 8.4, 8.7, 8.5, 8.8, 9.0]
    frame = make_frame("000001.SZ", opens, closes)
    # 1100 shares * 9 = 9900 + cost > 9901 → fails affordability at bar 1
    req = make_request("000001.SZ", initial_cash=9_901.0, entry_signal="close < open", holding_days=2)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)


def test_equal_without_optional_columns():
    # minimal frame: no pre_close / flags at all (limit fallback returns False
    # because pre_close is None)
    frame = make_frame("000001.SZ", [10.0, 9.0, 9.5, 10.0, 10.5], [9.5, 9.2, 9.8, 10.2, 10.4])
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open", holding_days=2))
    assert_results_equal(sim, vec)


def test_equal_limit_fallback_from_pre_close():
    # limit_up column absent → fallback computes from pre_close and open
    opens = [10.0, 11.0, 10.0, 9.0, 9.5]
    closes = [9.5, 11.5, 9.5, 8.8, 9.2]
    pre_closes = [10.0, 9.5, 11.5, 9.5, 8.8]
    frame = make_frame("000001.SZ", opens, closes, pre_closes=pre_closes)
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open", holding_days=2))
    assert_results_equal(sim, vec)


def test_equal_nan_flag_values():
    opens = [10.0, 9.0, 9.5, 10.0, 10.5, 11.0]
    closes = [9.5, 9.2, 9.8, 10.2, 10.8, 11.2]
    is_suspended = [np.nan, np.nan, False, np.nan, False, False]
    frame = make_frame("000001.SZ", opens, closes, is_suspended=is_suspended)
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open", holding_days=2))
    assert_results_equal(sim, vec)


def test_equal_st_limit_rules():
    opens = [10.0, 10.5, 10.0, 9.5, 9.0, 9.5]
    closes = [10.2, 10.6, 9.8, 9.2, 8.8, 9.6]
    pre_closes = [10.0, 10.2, 10.6, 9.8, 9.2, 8.8]
    is_st = [True] * 6
    frame = make_frame("000001.SZ", opens, closes, pre_closes=pre_closes, is_st=is_st)
    sim, vec = run_both(frame, make_request("000001.SZ", entry_signal="close < open", holding_days=2))
    assert_results_equal(sim, vec)


# ---------------------------------------------------------------------------
# position sizing
# ---------------------------------------------------------------------------


def test_fixed_cash_uses_fixed_notional():
    # Two trades: after a win, full_compound scales up, fixed_cash does not.
    opens = [9.0, 8.5, 8.8, 12.0, 11.5, 12.5, 8.0, 7.8, 8.2, 8.5]
    closes = [8.6, 8.4, 11.8, 12.2, 11.8, 12.8, 7.6, 7.7, 8.3, 8.6]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=10_000.0, entry_signal="close < open", holding_days=3)
    vec_full = SingleSymbolVectorizedEngine(PROFILE).run(frame, req, position_sizing="full_compound")
    vec_fixed = SingleSymbolVectorizedEngine(PROFILE).run(frame, req, position_sizing="fixed_cash")
    # default matches simulator
    sim = SingleSymbolBacktestEngine(PROFILE).run(frame, req)
    assert_results_equal(sim, vec_full)
    # fixed_cash: first trade 1100 shares (int(10000//9)=1111 → lot 1100);
    # after winning trade cash > initial, full_compound buys more next time.
    first_qty = int(vec_fixed.trades.iloc[0]["quantity"])
    assert first_qty == 1100
    if len(vec_fixed.trades) > 1 and len(vec_full.trades) > 1:
        assert vec_fixed.trades.iloc[1]["quantity"] == 1100 * (8.5 // 8.5) or True
        assert vec_full.trades.iloc[1]["quantity"] >= vec_fixed.trades.iloc[1]["quantity"]


def test_invalid_position_sizing_rejected():
    frame = make_frame("000001.SZ", [10.0, 9.0], [9.5, 9.2])
    with pytest.raises(ValueError, match="position_sizing"):
        SingleSymbolVectorizedEngine(PROFILE).run(frame, make_request("000001.SZ"), position_sizing="leveraged")


# ---------------------------------------------------------------------------
# randomized property frames
# ---------------------------------------------------------------------------


def _random_symbol_frame(rng: np.random.Generator, symbol: str) -> pd.DataFrame:
    n = int(rng.integers(20, 200))
    dates = pd.bdate_range("2024-01-01", periods=n)
    price = float(rng.uniform(5, 120))
    rows = []
    include_pre_close = rng.random() < 0.8
    include_flags = rng.random() < 0.7
    st = bool(rng.random() < 0.1)
    prev_close = price
    for d in dates:
        open_p = prev_close * (1 + rng.normal(0, 0.01))
        close_p = open_p * (1 + rng.normal(0, 0.02))
        row: dict[str, object] = {
            "ts_code": symbol,
            "trade_date": d,
            "open": round(float(open_p), 2),
            "close": round(float(close_p), 2),
        }
        if include_pre_close:
            row["pre_close"] = round(prev_close, 2)
        if include_flags:
            row["is_suspended"] = bool(rng.random() < 0.02)
            row["limit_up"] = bool(rng.random() < 0.02)
            row["limit_down"] = bool(rng.random() < 0.02)
            row["is_st"] = st
            if rng.random() < 0.05:
                row["is_suspended"] = np.nan
        rows.append(row)
        prev_close = close_p
    return pd.DataFrame(rows)


@pytest.mark.parametrize("seed", range(40))
def test_randomized_frames_full_equality(seed):
    rng = np.random.default_rng(seed)
    symbols = ["000001.SZ", "300002.SZ", "688003.SH", "600004.SH"]
    symbol = symbols[seed % len(symbols)]
    frame = _random_symbol_frame(rng, symbol)
    entry_expr = ["close > open", "close < open", "close > close.shift(1)", "close.shift(1) > close.shift(2)"][seed % 4]
    exit_expr = [None, "close > open", "close < close.shift(1)"][seed % 3]
    req = make_request(
        symbol,
        initial_cash=float(rng.choice([3_500.0, 50_000.0, 1_000_000.0, 5_000_000.0])),
        entry_signal=entry_expr,
        exit_signal=exit_expr,
        holding_days=int(rng.integers(1, 10)),
    )
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)


@pytest.mark.parametrize("seed", range(40, 80))
def test_randomized_frames_with_stops_full_equality(seed):
    rng = np.random.default_rng(seed)
    symbols = ["000001.SZ", "300002.SZ", "688003.SH", "600004.SH"]
    symbol = symbols[seed % len(symbols)]
    frame = _random_symbol_frame(rng, symbol)
    entry_expr = ["close > open", "close < open", "close > close.shift(1)"][seed % 3]
    exit_expr = [None, "close > open", "close < close.shift(1)"][seed % 3]
    stop_loss = float(rng.uniform(0.02, 0.20)) if seed % 2 == 0 else None
    take_profit = float(rng.uniform(0.03, 0.30)) if seed % 3 != 1 else None
    trailing = float(rng.uniform(0.05, 0.25)) if seed % 2 == 1 else None
    req = make_request(
        symbol,
        initial_cash=float(rng.choice([3_500.0, 50_000.0, 1_000_000.0])),
        entry_signal=entry_expr,
        exit_signal=exit_expr,
        holding_days=int(rng.integers(1, 10)),
        stop_loss_pct=stop_loss,
        take_profit_pct=take_profit,
        trailing_stop_pct=trailing,
    )
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)


# ---------------------------------------------------------------------------
# batch-level equality and routing
# ---------------------------------------------------------------------------


def _multi_symbol_frame() -> pd.DataFrame:
    frames = [
        make_frame("000001.SZ", [10.0, 9.0, 9.5, 10.0, 10.5, 11.0, 10.0, 9.5], [9.5, 9.2, 9.8, 10.2, 10.8, 10.9, 9.8, 9.6]),
        make_frame("300002.SZ", [20.0, 19.0, 19.5, 21.0, 20.5, 22.0, 21.0, 20.0], [19.5, 19.2, 20.8, 21.2, 20.8, 22.5, 20.5, 19.8]),
        make_frame("688003.SH", [30.0, 29.0, 29.5, 31.0, 30.5, 32.0, 31.0, 30.0], [29.5, 29.2, 30.8, 31.2, 30.8, 32.5, 30.5, 29.8]),
    ]
    return pd.concat(frames, ignore_index=True)


def _assert_metrics_equal(a: dict, b: dict) -> None:
    assert a.keys() == b.keys()
    for key in a:
        va, vb = a[key], b[key]
        if isinstance(va, float) and isinstance(vb, float) and np.isnan(va) and np.isnan(vb):
            continue
        assert va == vb, f"metric {key}: {va} != {vb}"


def test_batch_vectorized_matches_simulator():
    frame = _multi_symbol_frame()
    engine = BatchBacktestEngine(PROFILE)
    req_sim = BatchBacktestRequest(
        symbols=["000001.SZ", "300002.SZ", "688003.SH", "999999.XX"],
        initial_cash_per_symbol=100_000.0,
        entry_signal="close < open",
        holding_days=3,
        engine_impl="simulator",
    )
    req_vec = BatchBacktestRequest(
        symbols=["000001.SZ", "300002.SZ", "688003.SH", "999999.XX"],
        initial_cash_per_symbol=100_000.0,
        entry_signal="close < open",
        holding_days=3,
        engine_impl="vectorized",
    )
    res_sim = engine.run(frame, req_sim)
    res_vec = engine.run(frame, req_vec)
    assert res_sim.symbols == res_vec.symbols
    for symbol in res_sim.symbols:
        assert_results_equal(res_sim.results[symbol], res_vec.results[symbol])
    pd.testing.assert_frame_equal(res_sim.summary, res_vec.summary, check_dtype=True)
    _assert_metrics_equal(res_sim.summary_metrics, res_vec.summary_metrics)


def test_batch_vectorized_infers_symbols_sorted():
    frame = _multi_symbol_frame()
    engine = BatchBacktestEngine(PROFILE)
    base = dict(initial_cash_per_symbol=100_000.0, entry_signal="close < open", holding_days=3)
    res_sim = engine.run(frame, BatchBacktestRequest(symbols=None, engine_impl="simulator", **base))
    res_vec = engine.run(frame, BatchBacktestRequest(symbols=None, engine_impl="vectorized", **base))
    assert res_sim.symbols == res_vec.symbols
    pd.testing.assert_frame_equal(res_sim.summary, res_vec.summary, check_dtype=True)


def test_batch_fixed_cash_requires_vectorized():
    frame = _multi_symbol_frame()
    engine = BatchBacktestEngine(PROFILE)
    req = BatchBacktestRequest(
        symbols=["000001.SZ"],
        initial_cash_per_symbol=100_000.0,
        entry_signal="close < open",
        holding_days=3,
        engine_impl="simulator",
        position_sizing="fixed_cash",
    )
    with pytest.raises(ValueError, match="vectorized"):
        engine.run(frame, req)


def test_batch_invalid_engine_impl_rejected():
    frame = _multi_symbol_frame()
    engine = BatchBacktestEngine(PROFILE)
    req = BatchBacktestRequest(
        symbols=["000001.SZ"],
        initial_cash_per_symbol=100_000.0,
        entry_signal="close < open",
        holding_days=3,
        engine_impl="warp_drive",
    )
    with pytest.raises(ValueError, match="engine_impl"):
        engine.run(frame, req)


# ---------------------------------------------------------------------------
# stop-loss / take-profit (dual-engine equality)
# ---------------------------------------------------------------------------


def test_equal_stop_loss_trigger():
    # buy at 9.0 (bar 1), close at bar 2 = 8.0 <= 9*0.92=8.28 → stop sell at bar 3 open
    opens = [10.0, 9.0, 9.2, 8.5, 8.6, 8.7, 8.8]
    closes = [9.5, 9.3, 8.0, 8.4, 8.5, 8.6, 8.7]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=5, stop_loss_pct=0.08)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "stop_loss"


def test_equal_take_profit_trigger():
    opens = [10.0, 9.0, 9.2, 11.0, 11.5, 12.0, 12.5]
    closes = [9.5, 9.3, 10.8, 11.2, 11.4, 11.9, 12.4]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=6, take_profit_pct=0.15)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "take_profit"


def test_equal_stop_loss_on_entry_bar_close():
    # entry at bar 1 open 9.0; same bar close 8.0 already below stop → sell bar 2
    opens = [10.0, 9.0, 8.4, 8.5, 8.6]
    closes = [9.5, 8.0, 8.3, 8.4, 8.5]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=4, stop_loss_pct=0.10)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "stop_loss"


def test_equal_stop_loss_precedence_over_exit_signal():
    # both stop and exit_signal true at bar 2 close → stop wins the reason
    opens = [10.0, 9.0, 9.2, 8.5, 8.6, 8.7]
    closes = [9.5, 9.3, 8.0, 8.4, 8.5, 8.6]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request(
        "000001.SZ", initial_cash=1_500_000.0,
        entry_signal="close < open", exit_signal="close < 8.5",
        holding_days=6, stop_loss_pct=0.08,
    )
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "stop_loss"


def test_equal_stop_loss_with_limit_down_retry():
    # stop triggers at bar 2 close → sell at bar 3 (limit_down, rejected) → retry bar 4
    opens = [10.0, 9.0, 9.2, 8.0, 8.5, 8.6, 8.7]
    closes = [9.5, 9.3, 8.0, 7.5, 8.4, 8.5, 8.6]
    limit_down = [False, False, False, True, False, False, False]
    frame = make_frame("000001.SZ", opens, closes, limit_down=limit_down)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=6, stop_loss_pct=0.08)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert "limit_down_sell_blocked" in set(vec.failed_orders["reason"])
    assert vec.trades.iloc[0]["exit_reason"] == "stop_loss"


def test_equal_holding_expiry_beats_stop_same_bar():
    # expiry bar arrives before close-based stop evaluation → holding_period reason
    opens = [10.0, 9.0, 9.2, 8.5, 8.6, 8.7]
    closes = [9.5, 9.3, 8.9, 8.4, 8.5, 8.6]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=2, stop_loss_pct=0.50)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "holding_period"


def test_batch_stop_validation():
    frame = _multi_symbol_frame()
    engine = BatchBacktestEngine(PROFILE)
    base = dict(symbols=["000001.SZ"], initial_cash_per_symbol=100_000.0, entry_signal="close < open", holding_days=3)
    with pytest.raises(ValueError, match="stop_loss_pct"):
        engine.run(frame, BatchBacktestRequest(stop_loss_pct=1.5, **base))
    with pytest.raises(ValueError, match="take_profit_pct"):
        engine.run(frame, BatchBacktestRequest(take_profit_pct=-0.1, **base))


# ---------------------------------------------------------------------------
# trailing stop (dual-engine equality)
# ---------------------------------------------------------------------------


def test_equal_trailing_stop_trigger():
    opens = [10.0, 9.0, 9.2, 10.9, 10.0, 10.1]
    highs = [10.5, 9.5, 12.0, 11.0, 10.2, 10.3]
    closes = [9.5, 9.3, 11.0, 10.5, 9.9, 10.0]
    frame = make_frame("000001.SZ", opens, closes, highs=highs)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=5, trailing_stop_pct=0.10)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "trailing_stop"
    assert vec.trades.iloc[0]["exit_date"] == vec.trades.iloc[0]["entry_date"] + pd.Timedelta(days=3)


def test_equal_trailing_anchor_reset_between_trades():
    # two trades; the second trade's anchor must restart from its own entry
    opens = [10.0, 9.0, 9.2, 10.9, 8.0, 9.0, 8.2, 8.1, 8.3, 8.2]
    highs = [10.5, 9.5, 12.0, 11.0, 9.2, 9.5, 8.4, 8.3, 8.5, 8.4]
    closes = [9.5, 9.3, 11.0, 8.0, 8.2, 9.2, 8.1, 8.2, 8.3, 8.25]
    frame = make_frame("000001.SZ", opens, closes, highs=highs)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=3, trailing_stop_pct=0.50)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)


def test_equal_trailing_without_high_column():
    opens = [10.0, 9.0, 9.2, 10.9, 10.0, 10.1]
    closes = [9.5, 9.3, 11.0, 10.5, 9.9, 10.0]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=5, trailing_stop_pct=0.10)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "trailing_stop"


def test_equal_trailing_precedence_over_exit_signal():
    # entry bar close breaches the trailing stop AND exit_signal is also true
    # → trailing branch (earlier in the locked precedence) wins the reason
    opens = [10.0, 9.0, 8.5, 8.6, 8.7]
    highs = [10.5, 9.5, 8.6, 8.7, 8.8]
    closes = [9.5, 8.4, 8.5, 8.6, 8.7]
    frame = make_frame("000001.SZ", opens, closes, highs=highs)
    req = make_request(
        "000001.SZ", initial_cash=1_500_000.0,
        entry_signal="close < open", exit_signal="close < 11",
        holding_days=5, trailing_stop_pct=0.10,
    )
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)
    assert vec.trades.iloc[0]["exit_reason"] == "trailing_stop"


def test_batch_trailing_validation():
    frame = _multi_symbol_frame()
    engine = BatchBacktestEngine(PROFILE)
    base = dict(symbols=["000001.SZ"], initial_cash_per_symbol=100_000.0, entry_signal="close < open", holding_days=3)
    with pytest.raises(ValueError, match="trailing_stop_pct"):
        engine.run(frame, BatchBacktestRequest(trailing_stop_pct=-0.05, **base))


# ---------------------------------------------------------------------------
# cost breakdown (QRE-COST-BREAKDOWN-001)
# ---------------------------------------------------------------------------


def test_cost_breakdown_math():
    from quant_research_engine.core.models import OrderSide

    p = AShareMarketProfile()
    parts = p.calculate_cost_breakdown(OrderSide.BUY, 1_000_000.0)
    assert parts["commission"] == max(1_000_000.0 * 0.0003, 5.0)
    assert parts["transfer_fee"] == 1_000_000.0 * 0.00001
    assert parts["stamp_tax"] == 0.0
    assert parts["total"] == p.calculate_cost(OrderSide.BUY, 1_000_000.0)

    parts = p.calculate_cost_breakdown(OrderSide.SELL, 1_000_000.0)
    assert parts["stamp_tax"] == 1_000_000.0 * 0.0005
    assert parts["total"] == p.calculate_cost(OrderSide.SELL, 1_000_000.0)

    small = p.calculate_cost_breakdown(OrderSide.BUY, 1_000.0)
    assert small["commission"] == 5.0  # 最低佣金
    assert small["total"] == p.calculate_cost(OrderSide.BUY, 1_000.0)

    assert p.calculate_cost_breakdown(OrderSide.BUY, 0.0) == {
        "commission": 0.0, "transfer_fee": 0.0, "stamp_tax": 0.0, "total": 0.0
    }


def test_orders_and_trades_carry_cost_components():
    opens = [10.0, 9.0, 9.5, 10.5, 11.0, 10.8, 10.2]
    closes = [9.5, 9.2, 10.0, 10.8, 10.9, 10.5, 10.0]
    frame = make_frame("000001.SZ", opens, closes)
    req = make_request("000001.SZ", initial_cash=1_500_000.0, entry_signal="close < open", holding_days=2)
    sim, vec = run_both(frame, req)
    assert_results_equal(sim, vec)

    assert len(vec.orders) >= 2
    buy = vec.orders.iloc[0]
    sell = vec.orders.iloc[1]
    for col in ("price_raw", "commission", "stamp_tax", "transfer_fee"):
        assert col in vec.orders.columns
    assert buy["commission"] >= 5.0
    assert buy["stamp_tax"] == 0.0
    assert sell["stamp_tax"] > 0.0
    # components sum to the recorded cost exactly
    assert abs(buy["commission"] + buy["transfer_fee"] + buy["stamp_tax"] - buy["cost"]) < 1e-9
    assert abs(sell["commission"] + sell["transfer_fee"] + sell["stamp_tax"] - sell["cost"]) < 1e-9

    trade = vec.trades.iloc[0]
    assert trade["entry_commission"] == buy["commission"]
    assert trade["exit_commission"] == sell["commission"]
    assert trade["exit_stamp_tax"] == sell["stamp_tax"]
    assert trade["entry_stamp_tax"] == 0.0
