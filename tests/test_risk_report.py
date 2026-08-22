"""risk.report 单测：结构键齐全、参数回显、benchmark=None 降级、可 JSON 序列化。"""

from __future__ import annotations

import json

import numpy as np
import pytest

from quant_research_engine.risk.report import build_risk_report


@pytest.fixture()
def returns():
    rng = np.random.default_rng(31)
    return rng.standard_t(6, 400) * 0.012


@pytest.fixture()
def benchmark(returns):
    rng = np.random.default_rng(32)
    return 0.6 * returns + rng.normal(0, 0.008, len(returns))


class TestStructure:
    def test_top_level_keys(self, returns):
        report = build_risk_report(returns)
        assert set(report) == {"meta", "distribution", "tail", "volatility", "dependence", "performance"}

    def test_tail_three_methods_two_levels(self, returns):
        report = build_risk_report(returns)
        for level in ("95pct", "99pct"):
            assert set(report["tail"][level]) == {
                "parametric_normal", "historical_simulation", "ewma_parametric",
            }
            for method in report["tail"][level].values():
                assert "error" not in method
                assert method["es"] >= method["var"]

    def test_meta_param_echo(self, returns):
        report = build_risk_report(returns, config={"lam": 0.97, "risk_free_rate": 0.02})
        assert report["meta"]["ewma_lambda"] == pytest.approx(0.97)
        assert report["meta"]["risk_free_rate_annual"] == pytest.approx(0.02)
        assert report["meta"]["confidence_levels"] == [0.95, 0.99]
        assert report["meta"]["annualization_factor"] == 252
        assert report["meta"]["regime_quantiles"] == pytest.approx([1 / 3, 2 / 3])
        assert report["meta"]["n_obs"] == 400
        assert report["meta"]["has_benchmark"] is False
        assert report["volatility"]["ewma_latest"]["lambda"] == pytest.approx(0.97)
        assert report["performance"]["risk_free_rate_annual"] == pytest.approx(0.02)

    def test_volatility_sections(self, returns):
        report = build_risk_report(returns)
        assert "error" not in report["volatility"]["garch11"]
        assert report["volatility"]["garch11"]["stationary"] is True
        regime = report["volatility"]["regime"]
        assert regime["latest"] in {"low", "mid", "high"}
        assert sum(regime["counts"].values()) == 400

    def test_json_serializable(self, returns, benchmark):
        json.dumps(build_risk_report(returns, benchmark))


class TestBenchmarkHandling:
    def test_no_benchmark_null_sections(self, returns):
        report = build_risk_report(returns)
        assert report["dependence"]["spearman_vs_benchmark"] is None
        assert report["dependence"]["kendall_vs_benchmark"] is None
        assert report["performance"]["beta"] is None
        assert report["performance"]["jensens_alpha"] is None

    def test_with_benchmark_filled(self, returns, benchmark):
        report = build_risk_report(returns, benchmark)
        assert report["meta"]["has_benchmark"] is True
        spearman = report["dependence"]["spearman_vs_benchmark"]
        assert "error" not in spearman
        assert -1.0 <= spearman["coefficient"] <= 1.0
        assert report["performance"]["beta"] is not None
        assert report["performance"]["information_ratio"]["information_ratio"] is not None


class TestDegradation:
    def test_short_series_garch_error_but_report_built(self):
        """GARCH 需 ≥50 obs；短序列降级为 error 节而不抛异常。"""
        report = build_risk_report([0.01, -0.02, 0.03, 0.005, -0.01])
        assert "error" in report["volatility"]["garch11"]
        assert "error" not in report["tail"]["99pct"]["historical_simulation"]

    def test_too_short_raises_from_leaf(self):
        """叶子函数的参数校验仍硬失败（<2 obs）——但 report 降级为 error 节。"""
        report = build_risk_report([0.01])
        assert "error" in report["distribution"]
