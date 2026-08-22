"""risk.backtest_var 单测：HIT 手算、LR 统计量手算、独立性 LR 手算、多重检验公式。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from quant_research_engine.risk import backtest_var


class TestHitSeries:
    def test_hand_computed(self):
        """loss = −R；严格大于才算违约（L == VaR 不算）。"""
        returns = [-0.05, 0.01, -0.02, 0.0, -0.03]
        var = [0.03, 0.03, 0.03, 0.03, 0.03]
        hits = backtest_var.hit_series(returns, var)
        assert hits.tolist() == [1, 0, 0, 0, 0]

    def test_aligns_on_index_and_drops_nan(self):
        idx = pd.date_range("2024-01-01", periods=4, freq="B")
        returns = pd.Series([-0.05, np.nan, -0.01, 0.02], index=idx)
        var = pd.Series([0.02, 0.02, 0.02, np.nan], index=idx)
        hits = backtest_var.hit_series(returns, var)
        assert hits.tolist() == [1, 0]
        assert list(hits.index) == [idx[0], idx[2]]

    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            backtest_var.hit_series([0.01], [0.02])


class TestCoverageLr:
    def test_hand_computed_lr(self):
        """n=100, x=10, confidence=0.95（p=0.05, p̂=0.10）：
        LR = −2·[90·ln(0.95/0.90) + 10·ln(0.05/0.10)] = 4.13085（手算）。"""
        hits = [1] * 10 + [0] * 90
        result = backtest_var.coverage_lr_test(hits, confidence=0.95)
        expected = -2.0 * (90 * np.log(0.95 / 0.90) + 10 * np.log(0.05 / 0.10))
        assert expected == pytest.approx(4.13085, abs=1e-5)
        assert result["lr_statistic"] == pytest.approx(expected, rel=1e-12)
        assert result["p_value"] == pytest.approx(float(stats.chi2.sf(expected, 1)), rel=1e-12)
        assert result["violations"] == 10
        assert result["expected_violations"] == pytest.approx(5.0)
        assert result["violation_rate"] == pytest.approx(0.10)
        assert result["reject_5pct"] is True  # p ≈ 0.0421 < 0.05

    def test_exact_rate_gives_zero_lr(self):
        """违约率恰等于 1−p → p̂ = p → LR = 0，p 值 = 1。"""
        hits = [1] * 5 + [0] * 95
        result = backtest_var.coverage_lr_test(hits, confidence=0.95)
        assert result["lr_statistic"] == pytest.approx(0.0, abs=1e-12)
        assert result["p_value"] == pytest.approx(1.0)
        assert result["reject_5pct"] is False

    def test_zero_violations_edge(self):
        """x=0：LR = −2·n·ln(1−p)（0·ln0 按极限 0 处理），不 NaN。"""
        hits = [0] * 100
        result = backtest_var.coverage_lr_test(hits, confidence=0.95)
        expected = -2.0 * 100 * np.log(0.95)
        assert result["lr_statistic"] == pytest.approx(expected, rel=1e-12)
        assert np.isfinite(result["p_value"])

    def test_all_violations_edge(self):
        """x=n：LR = −2·n·ln(p），不 NaN。"""
        hits = [1] * 20
        result = backtest_var.coverage_lr_test(hits, confidence=0.95)
        expected = -2.0 * 20 * np.log(0.05)
        assert result["lr_statistic"] == pytest.approx(expected, rel=1e-12)
        assert result["reject_5pct"] is True

    def test_exact_binomial_matches_scipy(self):
        """教材方法①：违约次数精确二项检验，对 scipy binomtest。"""
        hits = [1] * 8 + [0] * 92
        result = backtest_var.coverage_lr_test(hits, confidence=0.95)
        expected = float(stats.binomtest(8, 100, 0.05).pvalue)
        assert result["exact_binomial_p_value"] == pytest.approx(expected, rel=1e-12)

    def test_non_binary_hits_raise(self):
        with pytest.raises(ValueError):
            backtest_var.coverage_lr_test([0, 2, 1, 0])


class TestIndependenceLr:
    def test_hand_computed_lr(self):
        """hits=[0,0,1,0,0,1,0,0] → n00=3, n01=2, n10=2, n11=0；
        π01=2/5, π11=0, π̄=2/7。LR = −2·[5·ln(5/7)+2·ln(2/7) − 3·ln(0.6)−2·ln(0.4)−2·ln(1.0)]。"""
        hits = [0, 0, 1, 0, 0, 1, 0, 0]
        result = backtest_var.independence_lr_test(hits)
        assert result["transitions"] == {"n00": 3, "n01": 2, "n10": 2, "n11": 0}
        assert result["pi_01"] == pytest.approx(0.4)
        assert result["pi_11"] == pytest.approx(0.0)
        assert result["pi_pooled"] == pytest.approx(2 / 7)
        log_null = 5 * np.log(5 / 7) + 2 * np.log(2 / 7)
        log_alt = 3 * np.log(0.6) + 2 * np.log(0.4) + 2 * np.log(1.0)
        expected = -2.0 * (log_null - log_alt)
        assert result["lr_statistic"] == pytest.approx(expected, rel=1e-12)
        assert result["p_value"] == pytest.approx(float(stats.chi2.sf(expected, 1)), rel=1e-12)

    def test_clustered_hits_rejected(self):
        """高持续 Markov 链（违约聚集）→ 大样本下独立性检验拒绝。"""
        rng = np.random.default_rng(7)
        n = 5000
        hits = np.zeros(n, dtype=int)
        for t in range(1, n):
            p = 0.8 if hits[t - 1] == 1 else 0.02
            hits[t] = int(rng.random() < p)
        result = backtest_var.independence_lr_test(hits)
        assert result["reject_5pct"] is True
        assert result["pi_11"] > result["pi_01"]

    def test_iid_hits_not_rejected(self):
        """iid Bernoulli → 独立性检验不拒绝（大样本）。"""
        rng = np.random.default_rng(7)
        hits = (rng.random(5000) < 0.05).astype(int)
        result = backtest_var.independence_lr_test(hits)
        assert result["reject_5pct"] is False
        assert result["pi_11"] == pytest.approx(result["pi_01"], abs=0.05)


class TestFalsePositive:
    def test_textbook_values(self):
        """书2 Ch6：α=0.05，n=10 → 40.1%；n=100 → 99.4%。"""
        assert backtest_var.false_positive_probability(0.05, 10) == pytest.approx(0.401263, abs=1e-6)
        assert backtest_var.false_positive_probability(0.05, 100) == pytest.approx(0.994079, abs=1e-6)

    def test_bad_alpha_raises(self):
        with pytest.raises(ValueError):
            backtest_var.false_positive_probability(1.5, 10)


class TestSummary:
    def test_unified_output_dict(self):
        rng = np.random.default_rng(3)
        returns = rng.normal(0, 0.01, 500)
        var = np.full(500, 0.025)  # 恒定 VaR，σ=0.01 → 违约率 ~0.62% < 1%
        result = backtest_var.backtest_var_summary(returns, var, confidence=0.99)
        for key in (
            "violations", "expected_violations", "violation_rate",
            "coverage", "independence", "reject_5pct", "conclusion",
        ):
            assert key in result
        assert result["violations"] == result["coverage"]["violations"]
        assert result["expected_violations"] == pytest.approx(500 * 0.01)

    def test_mismatched_var_detected(self):
        """VaR 系统性过小 → 覆盖率拒绝，结论文字对应。"""
        rng = np.random.default_rng(3)
        returns = rng.normal(0, 0.02, 500)
        var = np.full(500, 0.005)
        result = backtest_var.backtest_var_summary(returns, var, confidence=0.99)
        assert result["coverage"]["reject_5pct"] is True
        assert "覆盖率" in result["conclusion"]
