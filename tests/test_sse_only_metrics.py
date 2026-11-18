from __future__ import annotations

import json

import pytest

from quant_research_engine.portfolio.benchmark import excess_return_vs_sse


def test_excess_return_vs_sse_uses_arithmetic_difference():
    assert excess_return_vs_sse(0.20, 0.08) == pytest.approx(0.12)
    assert excess_return_vs_sse(-0.05, 0.08) == pytest.approx(-0.13)


def test_excess_return_vs_sse_never_falls_back_to_buy_hold():
    assert excess_return_vs_sse(0.20, None) is None
    assert excess_return_vs_sse(None, 0.08) is None


def test_strategy_performance_uses_sse_not_buy_hold():
    from quant_research_engine.portfolio.full_market_report import build_strategy_performance

    result = build_strategy_performance(
        {"date_start": "2026-01-01", "date_end": "2026-01-31"},
        benchmark_return=0.08,
    )
    assert result["benchmark_code"] == "000001.SH"
    assert result["benchmark_name"] == "上证指数"
    assert result["benchmark_return"] == pytest.approx(0.08)
    assert "buy_hold_return" not in result
    assert "excess_return_vs_buy_hold" not in result


def test_lab_chart_metrics_use_sse_curve(tmp_path):
    from quant_research_engine.gui import lab_result

    (tmp_path / "strategy_performance.json").write_text(json.dumps({
        "strategy_total_return": 0.20,
        "buy_hold_return": 9.0,
        "excess_return_vs_buy_hold": -8.8,
        "date_start": "2026-01-01",
        "date_end": "2026-01-03",
    }))
    (tmp_path / "equity_curve.csv").write_text(
        "trade_date,total_equity\n2026-01-01,100000\n2026-01-02,110000\n2026-01-03,120000\n"
    )
    record = {"run_id": "r1", "output_dir": str(tmp_path)}
    original = lab_result._benchmark_series
    lab_result._benchmark_series = lambda dates: ({
        "000001.SH": {"name": "上证指数", "dates": dates, "closes": [100.0, 104.0, 108.0]},
    }, None)
    try:
        data = lab_result.build_lab_chart_data(record)
    finally:
        lab_result._benchmark_series = original
    metrics = data["metrics"]
    assert metrics["benchmark_return"] == pytest.approx(0.08)
    assert metrics["excess_return"] == pytest.approx(0.12)
    assert metrics["excess_return_vs_benchmark"] == pytest.approx(0.12)
    assert "buy_hold_return" not in metrics
    assert "buy_hold_curve" not in data


def test_shared_chart_has_no_buy_hold_series():
    from pathlib import Path

    source = Path("src/quant_research_engine/gui/static/equity-chart.js").read_text()
    assert "holdPct" not in source
    assert "买入持有" not in source
