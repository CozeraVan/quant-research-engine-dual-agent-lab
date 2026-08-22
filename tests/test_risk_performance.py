"""risk.performance 单测：手算值核对 + 与引擎 portfolio/risk.py 口径一致性。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.risk import performance
from quant_research_engine.portfolio.risk import summarize_equity_curve


class TestSharpe:
    def test_hand_computed(self):
        """r=[0.01,0.02,−0.005]，rf=0：mean=0.008333，std(ddof=1)=0.0125831，
        Sharpe = mean/std·√252 ≈ 10.512。"""
        r = [0.01, 0.02, -0.005]
        result = performance.sharpe_ratio(r, risk_free_rate=0.0)
        arr = np.array(r)
        expected = arr.mean() / arr.std(ddof=1) * np.sqrt(252)
        assert result["sharpe"] == pytest.approx(expected, rel=1e-12)
        assert result["sharpe"] == pytest.approx(10.5131, abs=1e-3)

    def test_matches_engine_risk_py(self):
        """与引擎 portfolio/risk.py 的 Sharpe 同输入同值（口径一致性抽查）。"""
        rng = np.random.default_rng(10)
        daily = rng.normal(0.0004, 0.012, 300)
        equity = 1_000_000.0 * np.cumprod(1.0 + daily)
        curve = pd.DataFrame({"total_equity": np.concatenate([[1_000_000.0], equity])})
        engine_sharpe = summarize_equity_curve(
            curve, annualization_factor=252, risk_free_rate=0.03
        )["sharpe"]
        ours = performance.sharpe_ratio(daily, risk_free_rate=0.03)["sharpe"]
        # 引擎从净值反推的收益与我们直接给的收益在浮点尾数上略有差异
        assert ours == pytest.approx(engine_sharpe, rel=1e-9)

    def test_zero_vol_gives_none(self):
        assert performance.sharpe_ratio([0.01, 0.01, 0.01], risk_free_rate=0.0)["sharpe"] is None


class TestSortino:
    def test_hand_computed(self):
        """r=[0.02,−0.01,0.03]，T=0：shortfall=[0,−0.01,0]，
        downside dev=√(1e-4/3)，Sortino=mean/dev·√252。"""
        r = [0.02, -0.01, 0.03]
        result = performance.sortino_ratio(r, risk_free_rate=0.0, target=0.0)
        dev = np.sqrt((0.01**2) / 3.0)
        expected = np.mean(r) / dev * np.sqrt(252)
        assert result["sortino"] == pytest.approx(expected, rel=1e-12)
        assert result["sortino"] == pytest.approx(36.66, abs=1e-2)

    def test_no_downside_gives_none(self):
        assert performance.sortino_ratio([0.01, 0.02], risk_free_rate=0.0, target=0.0)["sortino"] is None


class TestTreynor:
    def test_hand_computed_exact_beta(self):
        """r = 2·m（β 恰为 2），rf=0：Treynor = mean(r)·252/2。"""
        m = np.array([0.01, -0.02, 0.03, 0.0])
        r = 2.0 * m
        result = performance.treynor_ratio(r, m, risk_free_rate=0.0)
        assert result["beta"] == pytest.approx(2.0, rel=1e-12)
        assert result["treynor"] == pytest.approx(r.mean() * 252 / 2.0, rel=1e-12)


class TestInformationRatio:
    def test_hand_computed(self):
        """active=[0.001,−0.002,0.003]：mean=0.0006667，std(ddof=1)=0.0025166，
        IR = mean/std·√252 ≈ 4.205。"""
        benchmark = np.array([0.01, 0.01, 0.01])
        active = np.array([0.001, -0.002, 0.003])
        r = benchmark + active
        result = performance.information_ratio(r, benchmark)
        expected = active.mean() / active.std(ddof=1) * np.sqrt(252)
        assert result["information_ratio"] == pytest.approx(expected, rel=1e-12)
        assert result["information_ratio"] == pytest.approx(4.205, abs=1e-3)
        assert result["tracking_error_daily"] == pytest.approx(active.std(ddof=1), rel=1e-12)

    def test_identical_series_gives_none(self):
        r = [0.01, -0.02, 0.03]
        assert performance.information_ratio(r, r)["information_ratio"] is None


class TestJensensAlpha:
    def test_exact_linear_recovery(self):
        """r = 0.001 + 1.5·m（rf=0）→ 回归截距恰为 0.001，年化 ×252。"""
        m = np.array([0.01, -0.02, 0.03, 0.005, -0.01])
        r = 0.001 + 1.5 * m
        result = performance.jensens_alpha(r, m, risk_free_rate=0.0)
        assert result["alpha_daily"] == pytest.approx(0.001, abs=1e-15)
        assert result["alpha_annual"] == pytest.approx(0.252, rel=1e-12)
        assert result["beta"] == pytest.approx(1.5, rel=1e-12)
        assert result["r_squared"] == pytest.approx(1.0)

    def test_beta_formula(self):
        """β = cov(R_i,R_M)/σ²_M（式 5.1）。"""
        rng = np.random.default_rng(4)
        m = rng.normal(0, 0.01, 200)
        r = 0.8 * m + rng.normal(0, 0.005, 200)
        expected = np.cov(r, m, ddof=1)[0, 1] / m.var(ddof=1)
        assert performance.beta(r, m) == pytest.approx(expected, rel=1e-12)

    def test_zero_market_variance_raises(self):
        with pytest.raises(ValueError):
            performance.beta([0.01, 0.02], [0.0, 0.0])


class TestPerformanceSummary:
    def test_without_benchmark_nulls(self):
        rng = np.random.default_rng(7)
        result = performance.performance_summary(rng.normal(0, 0.01, 100))
        assert result["sharpe"]["sharpe"] is not None
        assert result["sortino"]["sortino"] is not None
        assert result["beta"] is None
        assert result["treynor"] is None
        assert result["information_ratio"] is None
        assert result["jensens_alpha"] is None
        assert result["risk_free_rate_annual"] == pytest.approx(0.03)
        assert result["annualization_factor"] == 252

    def test_with_benchmark_filled(self):
        rng = np.random.default_rng(7)
        m = rng.normal(0.0005, 0.01, 100)
        r = 0.7 * m + rng.normal(0, 0.005, 100)
        result = performance.performance_summary(r, m)
        assert result["beta"] is not None
        assert result["treynor"]["treynor"] is not None
        assert result["information_ratio"]["information_ratio"] is not None
        assert result["jensens_alpha"]["alpha_daily"] is not None
