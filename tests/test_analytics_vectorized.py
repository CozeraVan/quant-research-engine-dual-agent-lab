"""Equality tests for the vectorized window/rolling batch analytics.

The collectors `_collect_window_return_rows` / `_collect_rolling_return_rows`
replaced per-symbol/per-window loops. The unchanged risk-module functions
serve as the reference oracle: expected outputs are computed through the old
code path and compared exactly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.portfolio.analytics import (
    _batch_rolling_summary_columns,
    _batch_window_summary_columns,
    _summarize_window_return_rows,
    summarize_batch_rolling_summary,
    summarize_batch_window_summary,
)
from quant_research_engine.portfolio.risk import (
    summarize_equity_curve_by_window,
    summarize_equity_curve_rolling,
)


def _oracle_window_summary(equity_curves, window):
    rows = []
    for symbol, equity_curve in equity_curves.items():
        symbol_windows = summarize_equity_curve_by_window(equity_curve, window=window)
        if symbol_windows.empty:
            continue
        for record in symbol_windows.to_dict("records"):
            rows.append(
                {
                    "window": record["window"],
                    "symbol": symbol,
                    "total_return": record["total_return"],
                }
            )
    if not rows:
        return pd.DataFrame(columns=_batch_window_summary_columns())
    return _summarize_window_return_rows(pd.DataFrame(rows), group_columns=["window"])


def _oracle_rolling_summary(equity_curves, window_size):
    rows = []
    for symbol, equity_curve in equity_curves.items():
        symbol_rolling = summarize_equity_curve_rolling(equity_curve, window_size=window_size)
        if symbol_rolling.empty:
            continue
        for record in symbol_rolling.to_dict("records"):
            rows.append(
                {
                    "window_size": record["window_size"],
                    "end_date": record["end_date"],
                    "symbol": symbol,
                    "total_return": record["total_return"],
                    "max_drawdown": record["max_drawdown"],
                }
            )
    if not rows:
        return pd.DataFrame(columns=_batch_rolling_summary_columns())
    return _summarize_window_return_rows(
        pd.DataFrame(rows),
        group_columns=["window_size", "end_date"],
        output_columns=_batch_rolling_summary_columns(),
    )


def _equity_curve(symbol_returns, start="2024-01-01", start_equity=100_000.0, freq="B"):
    n = len(symbol_returns)
    equity = [start_equity]
    for r in symbol_returns:
        equity.append(equity[-1] * (1 + r))
    return pd.DataFrame(
        {
            "trade_date": pd.date_range(start, periods=len(equity), freq=freq),
            "total_equity": equity,
        }
    )


def _sample_curves():
    rng = np.random.default_rng(11)
    return {
        "000001.SZ": _equity_curve(list(rng.normal(0.001, 0.02, 120))),
        "300002.SZ": _equity_curve(list(rng.normal(-0.002, 0.03, 90))),
        "688003.SH": _equity_curve(list(rng.normal(0.0, 0.01, 30))),
    }


def test_window_summary_matches_oracle_all_windows():
    curves = _sample_curves()
    for window in ("M", "Q", "Y"):
        expected = _oracle_window_summary(curves, window)
        actual = summarize_batch_window_summary(curves, window=window)
        pd.testing.assert_frame_equal(expected, actual, check_dtype=True)


def test_rolling_summary_matches_oracle_multiple_sizes():
    curves = _sample_curves()
    for window_size in (2, 5, 20, 60):
        expected = _oracle_rolling_summary(curves, window_size)
        actual = summarize_batch_rolling_summary(curves, window_size=window_size)
        pd.testing.assert_frame_equal(expected, actual, check_dtype=True)


def test_window_summary_empty_and_short_inputs():
    empty = pd.DataFrame(columns=["trade_date", "total_equity"])
    curves = {"000001.SZ": empty}
    expected = _oracle_window_summary(curves, "M")
    actual = summarize_batch_window_summary(curves, window="M")
    pd.testing.assert_frame_equal(expected, actual, check_dtype=False)

    short = {"000001.SZ": _equity_curve([0.01, 0.02])}
    expected = _oracle_rolling_summary(short, 20)
    actual = summarize_batch_rolling_summary(short, window_size=20)
    pd.testing.assert_frame_equal(expected, actual, check_dtype=False)


def test_window_summary_nan_and_nonpositive_start():
    curve = _equity_curve([0.01, -0.02, 0.03, 0.01])
    curve.loc[2, "total_equity"] = np.nan  # dropped row
    # zero start then positive: total_return must be NaN (start not > 0) but
    # the oracle's drawdown path stays computable (a fully-zero curve crashes
    # the pre-existing oracle — latent issue, unreachable from engine outputs).
    zero_start = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=3, freq="B"),
            "total_equity": [0.0, 10.0, 20.0],
        }
    )
    curves = {"000001.SZ": curve, "000002.SZ": zero_start}
    expected = _oracle_window_summary(curves, "Y")
    actual = summarize_batch_window_summary(curves, window="Y")
    pd.testing.assert_frame_equal(expected, actual, check_dtype=True)

    expected = _oracle_rolling_summary({"000002.SZ": zero_start}, 2)
    actual = summarize_batch_rolling_summary({"000002.SZ": zero_start}, window_size=2)
    pd.testing.assert_frame_equal(expected, actual, check_dtype=True)


def test_missing_required_columns_raises():
    bad = {"000001.SZ": pd.DataFrame({"trade_date": pd.date_range("2024-01-01", periods=3)})}
    with pytest.raises(ValueError, match="trade_date and total_equity"):
        summarize_batch_window_summary(bad, window="M")
    with pytest.raises(ValueError, match="trade_date and total_equity"):
        summarize_batch_rolling_summary(bad, window_size=2)


def test_random_curves_match_oracle():
    rng = np.random.default_rng(99)
    for trial in range(10):
        curves = {}
        for s in range(4):
            n = int(rng.integers(5, 250))
            curve = _equity_curve(list(rng.normal(0, 0.05, n)), start_equity=float(rng.uniform(1e3, 1e7)))
            if rng.random() < 0.5 and n > 5:
                curve.loc[rng.choice(n // 2, size=2, replace=False), "total_equity"] = np.nan
            curves[f"sym{s}"] = curve
        pd.testing.assert_frame_equal(
            _oracle_window_summary(curves, "M"),
            summarize_batch_window_summary(curves, window="M"),
            check_dtype=True,
        )
        pd.testing.assert_frame_equal(
            _oracle_rolling_summary(curves, 20),
            summarize_batch_rolling_summary(curves, window_size=20),
            check_dtype=True,
        )
