"""risk.inference 单测：已知分布 bootstrap 区间、MC 标准误、CBB/iid 对照、手算指标。"""

from __future__ import annotations

import numpy as np
import pytest

from quant_research_engine.risk import inference
from quant_research_engine.risk.constants import default_block_size


class TestBlockSize:
    def test_sqrt_rule(self):
        """书2 Ch13 经验法则 q≈√n（向上取整）。"""
        assert default_block_size(400) == 20
        assert default_block_size(750) == 28  # ceil(27.386...)
        assert default_block_size(1) == 1
        with pytest.raises(ValueError):
            default_block_size(0)


class TestMetricPointEstimates:
    def test_max_drawdown_hand_computed(self):
        """r=[0.1,−0.2,0.05] → 净值 1.1/0.88/0.924，峰 1.1 → 最大回撤 = 1−0.88/1.1 = 0.2。"""
        result = inference.bootstrap_metric_ci(
            [0.1, -0.2, 0.05, 0.01], metric="max_drawdown", n_bootstrap=10, seed=1
        )
        assert result["sample_statistic"] == pytest.approx(0.2, rel=1e-12)

    def test_annualized_return_hand_computed(self):
        returns = [0.01, -0.02, 0.03, 0.005, -0.015]
        result = inference.bootstrap_metric_ci(
            returns, metric="annualized_return", n_bootstrap=10, seed=1
        )
        assert result["sample_statistic"] == pytest.approx(np.mean(returns) * 252, rel=1e-12)

    def test_sharpe_matches_performance_convention(self):
        """夏普口径与 performance.sharpe_ratio 一致：(mean(r−rf/252)/std(ddof=1))·√252。"""
        rng = np.random.default_rng(9)
        returns = rng.normal(0.001, 0.02, 100)
        result = inference.bootstrap_metric_ci(
            returns, metric="sharpe", n_bootstrap=10, seed=1, risk_free_rate=0.03
        )
        expected = ((returns - 0.03 / 252).mean() / returns.std(ddof=1)) * np.sqrt(252)
        assert result["sample_statistic"] == pytest.approx(expected, rel=1e-12)

    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError):
            inference.bootstrap_metric_ci([0.01] * 10, metric="bogus")


class TestBootstrapIntervals:
    def test_ci_contains_truth_and_mc_error(self):
        """合成已知分布 N(0.001, 0.02)：固定 seed 的 95% CI 包含样本统计量；
        MC 标准误 = σ̂/√b（式 13.3）精确核对；块长默认 ceil(√n)。"""
        rng = np.random.default_rng(123)
        returns = rng.normal(0.001, 0.02, 400)
        result = inference.bootstrap_metric_ci(
            returns, metric="annualized_return", method="cbb", n_bootstrap=500, seed=7
        )
        assert result["block_size"] == 20
        assert result["ci_lower"] <= result["sample_statistic"] <= result["ci_upper"]
        assert result["mc_standard_error"] == pytest.approx(
            result["bootstrap_std"] / np.sqrt(500), rel=1e-12
        )
        assert result["bootstrap_std"] > 0

    def test_deterministic_given_seed(self):
        """教材：固定种子完全复现（监管合规）。"""
        rng = np.random.default_rng(11)
        returns = rng.normal(0.0, 0.015, 200)
        a = inference.bootstrap_metric_ci(returns, "sharpe", "cbb", 200, seed=42)
        b = inference.bootstrap_metric_ci(returns, "sharpe", "cbb", 200, seed=42)
        assert a["ci_lower"] == b["ci_lower"]
        assert a["ci_upper"] == b["ci_upper"]

    def test_iid_method_runs_and_differs(self):
        rng = np.random.default_rng(21)
        returns = rng.normal(0.0, 0.02, 300)
        result = inference.bootstrap_metric_ci(
            returns, "sharpe", method="iid", n_bootstrap=200, seed=5
        )
        assert result["block_size"] is None
        assert result["method"] == "iid"
        assert "低估" in result["note"]

    def test_bad_method_raises(self):
        with pytest.raises(ValueError):
            inference.bootstrap_metric_ci([0.01] * 10, method="bootstrap")


class TestCbbVsIid:
    def test_iid_underestimates_under_serial_dependence(self):
        """书2 Ch13：iid bootstrap 破坏时间依赖。AR(1) φ=0.6 序列（策略收益
        自相关 + A 股波动聚类同属序列依赖）下，夏普/年化收益的 iid
        bootstrap 离散度显著低于 CBB——iid 把高低波动期均衡化，低估不确定性。"""
        rng = np.random.default_rng(77)
        innovations = rng.normal(0, 0.02, 400)
        returns = np.empty(400)
        for t in range(1, 400):
            returns[t] = 0.6 * returns[t - 1] + innovations[t]
        summary = inference.bootstrap_summary(
            returns,
            metrics=("sharpe", "annualized_return"),
            n_bootstrap=1000,
            seed=13,
        )
        for metric in ("sharpe", "annualized_return"):
            entry = summary[metric]
            assert entry["cbb"]["bootstrap_std"] > entry["iid"]["bootstrap_std"]
            assert entry["iid_underestimates"] is True

    def test_summary_structure(self):
        rng = np.random.default_rng(3)
        returns = rng.normal(0.0005, 0.01, 250)
        summary = inference.bootstrap_summary(returns, n_bootstrap=100, seed=1)
        assert set(summary) == {"annualized_return", "sharpe", "max_drawdown"}
        for entry in summary.values():
            assert set(entry) >= {"cbb", "iid", "iid_underestimates"}
            assert entry["cbb"]["mc_standard_error"] > 0
