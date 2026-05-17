import pandas as pd
import pytest

from quant_research_engine.portfolio.benchmark import summarize_benchmark_relative_performance


def test_summarize_benchmark_relative_performance_aligns_dates_and_metrics():
    equity_curve = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
            "total_equity": [100.0, 110.0, 121.0, 108.9],
        }
    )
    benchmark = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
            "close": [1000.0, 1050.0, 997.5, 1097.25],
        }
    )

    summary = summarize_benchmark_relative_performance(equity_curve, benchmark)

    assert summary["aligned_period_count"] == 4
    assert summary["return_observation_count"] == 3
    assert summary["portfolio_total_return"] == pytest.approx(0.089)
    assert summary["benchmark_total_return"] == pytest.approx(0.09725)
    assert summary["excess_total_return"] == pytest.approx(-0.00825)
    assert summary["tracking_error"] == pytest.approx(2.8618176042508385)
    assert summary["information_ratio"] == pytest.approx(0.0)
    assert summary["beta"] == pytest.approx(-1.1428571428571428)
    assert summary["alpha"] == pytest.approx(0.07142857142857142)
    assert summary["up_capture"] == pytest.approx(0.0)
    assert summary["down_capture"] == pytest.approx(-2.0)


def test_summarize_benchmark_relative_performance_handles_empty_overlap():
    equity_curve = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-01-01"]), "total_equity": [100.0]}
    )
    benchmark = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-02-01"]), "close": [1000.0]}
    )

    summary = summarize_benchmark_relative_performance(equity_curve, benchmark)

    assert summary["aligned_period_count"] == 0
    assert summary["return_observation_count"] == 0
    assert summary["portfolio_total_return"] is None
    assert summary["benchmark_total_return"] is None
    assert summary["information_ratio"] is None
