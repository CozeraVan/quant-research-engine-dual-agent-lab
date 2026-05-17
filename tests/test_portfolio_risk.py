import pandas as pd
import pytest

from quant_research_engine.portfolio.risk import (
    summarize_equity_curve,
    summarize_equity_curve_by_window,
    summarize_equity_curve_rolling,
)


def test_summarize_equity_curve_computes_core_daily_risk_metrics():
    equity_curve = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
            ),
            "total_equity": [100.0, 110.0, 99.0, 105.0, 120.0],
        }
    )

    metrics = summarize_equity_curve(equity_curve, annualization_factor=252)

    returns = pd.Series([0.10, -0.10, 105.0 / 99.0 - 1, 120.0 / 105.0 - 1])
    assert metrics["period_count"] == 5
    assert metrics["daily_return_count"] == 4
    assert metrics["start_equity"] == 100.0
    assert metrics["end_equity"] == 120.0
    assert metrics["total_return"] == pytest.approx(0.20)
    assert metrics["max_drawdown"] == pytest.approx(-0.10)
    assert metrics["max_drawdown_peak_date"] == "2026-01-06"
    assert metrics["max_drawdown_trough_date"] == "2026-01-07"
    assert metrics["max_drawdown_recovery_date"] == "2026-01-09"
    assert metrics["max_drawdown_duration_days"] == 1
    assert metrics["annualized_return"] == pytest.approx(1.2**(252 / 4) - 1)
    assert metrics["annualized_volatility"] == pytest.approx(float(returns.std()) * 252**0.5)
    assert metrics["sharpe"] == pytest.approx(float(returns.mean() / returns.std()) * 252**0.5)
    assert metrics["return_drawdown_ratio"] == pytest.approx(2.0)


def test_summarize_equity_curve_reports_unrecovered_drawdown():
    equity_curve = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
            "total_equity": [100.0, 120.0, 90.0],
        }
    )

    metrics = summarize_equity_curve(equity_curve)

    assert metrics["max_drawdown"] == pytest.approx(-0.25)
    assert metrics["max_drawdown_peak_date"] == "2026-01-06"
    assert metrics["max_drawdown_trough_date"] == "2026-01-07"
    assert metrics["max_drawdown_recovery_date"] is None
    assert metrics["max_drawdown_duration_days"] == 1


def test_summarize_equity_curve_handles_empty_curve():
    metrics = summarize_equity_curve(pd.DataFrame())

    assert metrics["period_count"] == 0
    assert metrics["total_return"] is None
    assert metrics["max_drawdown"] is None
    assert metrics["max_drawdown_peak_date"] is None
    assert metrics["max_drawdown_trough_date"] is None
    assert metrics["max_drawdown_recovery_date"] is None
    assert metrics["max_drawdown_duration_days"] is None


def test_summarize_equity_curve_by_window_computes_monthly_metrics():
    equity_curve = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2026-01-29", "2026-01-30", "2026-02-02", "2026-02-03", "2026-02-04"]
            ),
            "total_equity": [100.0, 110.0, 120.0, 108.0, 126.0],
        }
    )

    windows = summarize_equity_curve_by_window(equity_curve, window="M", annualization_factor=252)

    assert windows["window"].tolist() == ["2026-01", "2026-02"]
    assert windows["start_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-29", "2026-02-02"]
    assert windows["end_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-30", "2026-02-04"]
    assert windows["period_count"].tolist() == [2, 3]
    assert windows["daily_return_count"].tolist() == [1, 2]
    assert windows["start_equity"].tolist() == [100.0, 120.0]
    assert windows["end_equity"].tolist() == [110.0, 126.0]
    assert windows["total_return"].tolist() == pytest.approx([0.10, 0.05])
    assert windows["max_drawdown"].tolist() == pytest.approx([0.0, -0.10])
    assert windows["max_drawdown_peak_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-29", "2026-02-02"]
    assert windows["max_drawdown_trough_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-29", "2026-02-03"]
    assert windows["max_drawdown_recovery_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-29", "2026-02-04"]
    assert windows["max_drawdown_duration_days"].tolist() == [0, 1]


def test_summarize_equity_curve_by_window_rejects_unsupported_window():
    equity_curve = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [100.0]}
    )

    with pytest.raises(ValueError, match="window"):
        summarize_equity_curve_by_window(equity_curve, window="W")


def test_summarize_equity_curve_rolling_computes_trailing_observation_windows():
    equity_curve = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
            ),
            "total_equity": [100.0, 110.0, 99.0, 105.0, 120.0],
        }
    )

    rolling = summarize_equity_curve_rolling(equity_curve, window_size=3, annualization_factor=252)

    assert rolling["window_size"].tolist() == [3, 3, 3]
    assert rolling["start_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]
    assert rolling["end_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-01-07",
        "2026-01-08",
        "2026-01-09",
    ]
    assert rolling["period_count"].tolist() == [3, 3, 3]
    assert rolling["total_return"].tolist() == pytest.approx([-0.01, 105.0 / 110.0 - 1, 120.0 / 99.0 - 1])
    assert rolling["max_drawdown"].tolist() == pytest.approx([-0.10, -0.10, 0.0])
    assert rolling["max_drawdown_peak_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-01-06",
        "2026-01-06",
        "2026-01-07",
    ]


def test_summarize_equity_curve_rolling_rejects_invalid_window_size():
    equity_curve = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [100.0]}
    )

    with pytest.raises(ValueError, match="window_size"):
        summarize_equity_curve_rolling(equity_curve, window_size=1)
