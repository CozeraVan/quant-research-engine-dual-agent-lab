"""risk.tail 单测：教材例题解析值 + 手算核对 + scipy 对照。"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from quant_research_engine.risk import tail
from quant_research_engine.risk.constants import Z_95, Z_99


class TestParametricNormalVarEs:
    def test_textbook_example_book4_ch1_eq17(self):
        """书4 Ch1 式 1.7 教材例题：μ=−20, σ=30, X=99% → VaR=49.79, ES=59.96。

        构造收益序列使损失（=−R）均值 −20、std(ddof=1) 恰为 30：
        两点 m±d 的 std = d·√2，故 d = 30/√2。
        """
        d = 30.0 / np.sqrt(2.0)
        returns = [20.0 - d, 20.0 + d]  # 收益均值 20 → 损失均值 −20
        result = tail.parametric_normal_var_es(returns, confidence=0.99)
        assert result["var"] == pytest.approx(49.79, abs=1e-2)
        assert result["es"] == pytest.approx(59.96, abs=1e-2)

    def test_z_values_match_textbook(self):
        """教材记 1.645/2.326；scipy 精确值 1.64485/2.32635。"""
        assert Z_95 == pytest.approx(1.64485, abs=1e-5)
        assert Z_99 == pytest.approx(2.32635, abs=1e-5)

    def test_matches_scipy_formulas(self):
        rng = np.random.default_rng(11)
        returns = rng.normal(0.0005, 0.02, 500)
        result = tail.parametric_normal_var_es(returns, 0.95)
        loss = -returns
        mu, sigma = loss.mean(), loss.std(ddof=1)
        z = stats.norm.ppf(0.95)
        assert result["var"] == pytest.approx(mu + sigma * z, rel=1e-12)
        assert result["es"] == pytest.approx(mu + sigma * stats.norm.pdf(z) / 0.05, rel=1e-12)

    def test_es_greater_equal_var(self):
        rng = np.random.default_rng(2)
        returns = rng.standard_t(5, 300)
        for level in (0.95, 0.99):
            result = tail.parametric_normal_var_es(returns, level)
            assert result["es"] >= result["var"]


class TestHistoricalVarEs:
    def test_known_losses_ordered_statistic(self):
        """已知损失序列 [1,2,3,4,5]：60% 分位（线性插值）= 3.4；
        ES = 不低于 VaR 的损失均值 = mean([4,5]) = 4.5。"""
        returns = [-1.0, -2.0, -3.0, -4.0, -5.0]
        result = tail.historical_var_es(returns, confidence=0.60)
        assert result["var"] == pytest.approx(3.4)
        assert result["es"] == pytest.approx(4.5)
        assert result["tail_count"] == 2
        assert result["interpolation"] == "linear"

    def test_textbook_500_scenarios_rule(self):
        """书4 Ch2：500 情景 99% VaR ≈ 第 5 大损失邻域（线性插值口径）。"""
        losses = np.arange(1.0, 501.0)  # 1..500
        returns = -losses
        result = tail.historical_var_es(returns, 0.99)
        # 升序 99% 分位，位置 0.99·499 = 494.01 → 495.01
        assert result["var"] == pytest.approx(495.01)
        assert result["es"] == pytest.approx(np.mean([496.0, 497.0, 498.0, 499.0, 500.0]))

    def test_es_greater_equal_var_random(self):
        rng = np.random.default_rng(5)
        returns = rng.standard_t(4, 400) * 0.01
        for level in (0.95, 0.99):
            result = tail.historical_var_es(returns, level)
            assert result["es"] >= result["var"]

    def test_bad_confidence_raises(self):
        with pytest.raises(ValueError):
            tail.historical_var_es([0.01, -0.02, 0.03], confidence=1.5)


class TestEwmaParametricVarEs:
    def test_uses_latest_ewma_sigma(self):
        rng = np.random.default_rng(9)
        returns = rng.normal(0.0, 0.015, 250)
        result = tail.ewma_parametric_var_es(returns, 0.99)
        from quant_research_engine.risk.volatility import ewma_variance_series

        expected_sigma = float(np.sqrt(ewma_variance_series(returns).iloc[-1]))
        assert result["sigma_forecast"] == pytest.approx(expected_sigma, rel=1e-12)
        assert result["lambda"] == pytest.approx(0.94)
        assert result["es"] >= result["var"]


class TestSkewKurtosis:
    def test_matches_scipy_both_conventions(self):
        rng = np.random.default_rng(21)
        returns = rng.standard_t(6, 800) * 0.01
        result = tail.skew_kurtosis(returns)
        arr = np.asarray(returns)
        assert result["skew_sample"] == pytest.approx(stats.skew(arr, bias=True), rel=1e-12)
        assert result["kurtosis_sample"] == pytest.approx(stats.kurtosis(arr, bias=True, fisher=False), rel=1e-12)
        assert result["skew_bias_corrected"] == pytest.approx(stats.skew(arr, bias=False), rel=1e-12)
        assert result["kurtosis_bias_corrected"] == pytest.approx(
            stats.kurtosis(arr, bias=False, fisher=False), rel=1e-12
        )
        assert result["excess_kurtosis_sample"] == pytest.approx(result["kurtosis_sample"] - 3.0)

    def test_sample_analog_hand_computed(self):
        """书2 Ch5 sample analog：ŝ=μ̂3/σ̂³、k̂=μ̂4/σ̂⁴（1/n 口径）。"""
        arr = np.array([0.01, -0.02, 0.03, 0.005, -0.015])
        mu = arr.mean()
        sigma = np.sqrt(np.mean((arr - mu) ** 2))  # 1/n 口径
        expected_skew = np.mean((arr - mu) ** 3) / sigma**3
        expected_kurt = np.mean((arr - mu) ** 4) / sigma**4
        result = tail.skew_kurtosis(arr)
        assert result["skew_sample"] == pytest.approx(expected_skew, rel=1e-12)
        assert result["kurtosis_sample"] == pytest.approx(expected_kurt, rel=1e-12)


class TestJarqueBera:
    def test_normal_sample_not_rejected(self):
        rng = np.random.default_rng(0)
        result = tail.jarque_bera_test(rng.normal(0.0, 1.0, 2000))
        assert result["p_value"] > 0.05
        assert result["reject_normal_5pct"] is False

    def test_fat_tail_sample_rejected(self):
        rng = np.random.default_rng(0)
        result = tail.jarque_bera_test(rng.standard_t(4, 2000))
        assert result["p_value"] < 0.05
        assert result["reject_normal_5pct"] is True
        assert result["jb_statistic"] > result["critical_5pct"]

    def test_matches_scipy(self):
        rng = np.random.default_rng(4)
        arr = rng.normal(0.0, 0.01, 300)
        result = tail.jarque_bera_test(arr)
        expected = stats.jarque_bera(arr)
        assert result["jb_statistic"] == pytest.approx(float(expected.statistic), rel=1e-12)


class TestDistributionSummary:
    def test_keys_and_robust_stats(self):
        rng = np.random.default_rng(8)
        returns = rng.normal(0.001, 0.02, 500)
        result = tail.distribution_summary(returns)
        for key in (
            "n_obs", "mean", "std", "median", "q25", "q75", "iqr",
            "skew_sample", "kurtosis_sample", "jb_statistic", "jb_p_value",
            "reject_normal_5pct", "annualization_factor",
        ):
            assert key in result
        assert result["n_obs"] == 500
        assert result["iqr"] == pytest.approx(result["q75"] - result["q25"])
        assert result["annualization_factor"] == 252

    def test_insufficient_data_raises(self):
        with pytest.raises(ValueError):
            tail.distribution_summary([0.01])
