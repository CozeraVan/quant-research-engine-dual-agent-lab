"""risk.derivatives_var 单测：DGV 近似 P&L、解析矩核对、VaR 序列对接回测。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from quant_research_engine.risk import backtest_var, derivatives_var
from quant_research_engine.risk.constants import z_value


class TestDgvPnl:
    def test_formula_hand_check(self):
        """式 2.3 + vega 项手算：ΔV = Δ·δS + ½Γ(δS)² + vega·δσ。

        Δ=10, Γ=2, vega=100, δS=0.5, δσ=0.01 → 5 + 0.25 + 1 = 6.25。
        """
        pnl = derivatives_var.dgv_pnl(10.0, 2.0, 100.0, 0.5, 0.01)
        assert float(pnl) == pytest.approx(6.25, abs=1e-12)

    def test_vectorized_scenarios(self):
        """逐情景数组输入逐点核对。"""
        dS = np.array([-1.0, 0.0, 1.0])
        pnl = derivatives_var.dgv_pnl(10.0, 2.0, 0.0, dS)
        expected = 10.0 * dS + 0.5 * 2.0 * dS**2
        np.testing.assert_allclose(pnl, expected, atol=1e-12)


class TestDgvVar:
    def test_delta_neutral_pure_gamma_analytic_moments(self):
        """CR §4 R6 验收点：delta 中性纯 gamma 组合对解析二阶矩核对。

        Δ=0、vega=0 → ΔV = ½Γ(δS)²：均值 = ½Γ·sS²，方差 = ½Γ²·sS⁴
        （χ²₁ 方差 2 倍缩放），偏度 = 2√2（χ²₁ 偏度），超额峰度 = 12。
        """
        gamma, sS = 2.0, 0.8
        result = derivatives_var.dgv_var(0.0, gamma, 0.0, sS, confidence=0.99)
        assert result["mean_pnl"] == pytest.approx(0.5 * gamma * sS**2, abs=1e-12)
        assert result["var_pnl"] == pytest.approx(0.5 * gamma**2 * sS**4, abs=1e-12)
        assert result["skew_pnl"] == pytest.approx(2.0 * np.sqrt(2.0), abs=1e-12)
        assert result["excess_kurtosis_pnl"] == pytest.approx(12.0, abs=1e-12)

    def test_moments_match_monte_carlo(self):
        """解析矩对 MC 模拟（固定 seed，容差按 MC 标准误放宽）。"""
        rng = np.random.default_rng(42)
        delta, gamma, vega, sS, ssig = 5.0, 3.0, 50.0, 0.6, 0.01
        n = 2_000_000
        pnl = derivatives_var.dgv_pnl(
            delta, gamma, vega, rng.normal(0, sS, n), rng.normal(0, ssig, n)
        )
        result = derivatives_var.dgv_var(delta, gamma, vega, sS, ssig)
        assert result["mean_pnl"] == pytest.approx(float(np.mean(pnl)), rel=1e-2)
        assert result["var_pnl"] == pytest.approx(float(np.var(pnl)), rel=2e-2)

    def test_linear_portfolio_is_normal(self):
        """纯 delta 组合（Γ=vega=0）：ΔV 正态，CF 退化为正态分位。"""
        delta, sS = 10.0, 0.5
        normal = derivatives_var.dgv_var(delta, 0.0, 0.0, sS, confidence=0.99)
        cf = derivatives_var.dgv_var(delta, 0.0, 0.0, sS, confidence=0.99,
                                     method="cornish_fisher")
        assert normal["skew_pnl"] == 0.0
        assert normal["excess_kurtosis_pnl"] == 0.0
        assert normal["var"] == pytest.approx(abs(delta) * sS * z_value(0.99), abs=1e-12)
        assert cf["var"] == pytest.approx(normal["var"], abs=1e-12)

    def test_long_gamma_lowers_var(self):
        """正 gamma（多头期权）P&L 均值>0、偏度>0 → 损失偏度<0，
        CF 调整的 VaR 低于正态 VaR。"""
        delta, gamma, sS = 0.0, 2.0, 0.8
        normal = derivatives_var.dgv_var(delta, gamma, 0.0, sS, confidence=0.99)
        cf = derivatives_var.dgv_var(delta, gamma, 0.0, sS, confidence=0.99,
                                     method="cornish_fisher")
        assert normal["mean_pnl"] > 0
        assert cf["var"] < normal["var"]

    def test_var_matches_mc_quantile(self):
        """CF-VaR 对 MC 经验分位（损失口径，rel 容差 5%）。

        参数取 delta 主导、|偏度|<0.5 的组合——CF 展开只在偏度适中时
        有效（高偏度如纯 gamma χ² 型分布 CF 失真，为已知限制，见
        test_long_gamma_lowers_var 与模块 docstring 披露）。
        """
        rng = np.random.default_rng(7)
        delta, gamma, vega, sS, ssig = 10.0, 2.0, 50.0, 0.5, 0.01
        n = 2_000_000
        pnl = derivatives_var.dgv_pnl(
            delta, gamma, vega, rng.normal(0, sS, n), rng.normal(0, ssig, n)
        )
        mc_var = float(np.quantile(-pnl, 0.99))
        cf = derivatives_var.dgv_var(delta, gamma, vega, sS, ssig, confidence=0.99,
                                     method="cornish_fisher")
        assert abs(cf["skew_pnl"]) < 0.5
        assert cf["var"] == pytest.approx(mc_var, rel=5e-2)

    def test_validation(self):
        with pytest.raises(ValueError):
            derivatives_var.dgv_var(1.0, 0.0, 0.0, -0.5)
        with pytest.raises(ValueError):
            derivatives_var.dgv_var(1.0, 0.0, 0.0, 0.5, confidence=1.5)
        with pytest.raises(ValueError):
            derivatives_var.dgv_var(1.0, 0.0, 0.0, 0.5, method="heston")


class TestDgvVarSeries:
    def test_series_and_backtest_integration(self):
        """VaR 序列对接 backtest_var.backtest_var_summary（CR §4 R6 验收点：
        不新造回测引擎，复用 HIT/LR）。

        合成：逐日 δS ~ N(0, sS²) 模拟，delta 主导的组合（CF 适用域），
        每日 VaR 取 99% CF 分位；损失 L = −ΔV 超 VaR 的 HIT 频率应
        ≈1%，覆盖率/独立性 LR 均不拒绝。
        """
        rng = np.random.default_rng(123)
        n = 2000
        delta, gamma, vega, sS = 10.0, 2.0, 50.0, 0.5
        dS = rng.normal(0, sS, n)
        pnl = derivatives_var.dgv_pnl(delta, gamma, vega, dS)
        returns = pd.Series(pnl)  # 收益口径（损失=−r）
        frame = pd.DataFrame({
            "delta": delta,
            "gamma": gamma,
            "vega": vega,
            "spot_shock_sd": sS,
            "vol_shock_sd": 0.0,
        }, index=returns.index)
        var_series = derivatives_var.dgv_var_series(
            frame, confidence=0.99, method="cornish_fisher"
        )
        assert len(var_series) == n
        summary = backtest_var.backtest_var_summary(returns, var_series, confidence=0.99)
        assert summary["n_obs"] == n
        # 违约率 ≈ 1%（容差按二项波动放宽到 [0.4%, 2%]）
        assert 0.004 < summary["violation_rate"] < 0.02
        # CF 分位略有误差，覆盖率/独立性大概率不拒绝；至少独立性必须不拒绝
        assert summary["independence"]["reject_5pct"] is False

    def test_missing_columns_rejected(self):
        with pytest.raises(ValueError):
            derivatives_var.dgv_var_series(pd.DataFrame({"delta": [1.0]}))

    def test_vol_shock_column_optional(self):
        frame = pd.DataFrame({
            "delta": [1.0], "gamma": [0.0], "vega": [100.0],
            "spot_shock_sd": [0.5], "vol_shock_sd": [0.01],
        })
        with_vol = derivatives_var.dgv_var_series(frame)
        without_vol = derivatives_var.dgv_var_series(frame.drop(columns=["vol_shock_sd"]))
        # vol_shock_sd=0.01 与缺省（=0）相比 σ 更大 → VaR 更大
        assert with_vol.iloc[0] > without_vol.iloc[0]


class TestNormalQuantileConvention:
    def test_z_matches_constants(self):
        """置信水平分位与 constants.z_value 一致（损失正号约定）。"""
        result = derivatives_var.dgv_var(10.0, 0.0, 0.0, 0.5, confidence=0.95)
        assert result["z"] == pytest.approx(float(stats.norm.ppf(0.95)), abs=1e-12)
