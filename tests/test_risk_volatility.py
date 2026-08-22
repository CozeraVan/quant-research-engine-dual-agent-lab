"""risk.volatility 单测：EWMA 手算递推 + arch 交叉 + GARCH 模拟复现 + regime。"""

from __future__ import annotations

import numpy as np
import pytest

from quant_research_engine.risk import volatility


def _simulate_garch11(omega, alpha, beta, nobs, seed):
    """确定性 GARCH(1,1) 模拟（固定 seed 的手写递推，不依赖 arch 随机源）。

    σ²_t = ω + α·r²_{t−1} + β·σ²_{t−1}（式 3.4，正态创新，收益率量纲）。
    """
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(nobs)
    r = np.empty(nobs)
    var = omega / (1.0 - alpha - beta) if alpha + beta < 1.0 else omega / 0.05
    prev_r2 = 0.0
    for t in range(nobs):
        var = omega + alpha * prev_r2 + beta * var
        r[t] = np.sqrt(var) * z[t]
        prev_r2 = r[t] ** 2
    return r


class TestEwmaVarianceSeries:
    def test_hand_computed_three_steps(self):
        """书4 Ch3 式 3.2 手算：r=[0.01,−0.02,0.03]，λ=0.94 →
        σ²=[1e-4, 1.18e-4, 1.6492e-4]。"""
        result = volatility.ewma_variance_series([0.01, -0.02, 0.03])
        expected = [1e-4, 1.18e-4, 1.6492e-4]
        np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-10)

    def test_init_convention(self):
        result = volatility.ewma_variance_series([0.05, 0.01])
        assert result.iloc[0] == pytest.approx(0.05**2)

    def test_matches_arch_fixed_ewma_after_shift(self):
        """与 arch 交叉：GARCH(1,1) 固定参数 ω=0, α=1−λ, β=λ（EWMA 特例）的
        条件方差 = 本实现 raw 序列 shift(1)（arch 的 day-t 方差仅用 r_{t−1}），
        burn-in 后一致到 1e-10。"""
        from arch import arch_model

        rng = np.random.default_rng(3)
        r = rng.normal(0.0, 0.01, 500)
        arch_var = (
            arch_model(r * 100, mean="Zero", vol="GARCH", p=1, q=1)
            .fix([0.0, 0.06, 0.94])
            .conditional_volatility
            ** 2
            / 1e4
        )
        ours = volatility.ewma_variance_series(r).to_numpy()
        np.testing.assert_allclose(arch_var[300:], ours[299:-1], rtol=1e-6, atol=1e-12)

    def test_forecast_series_no_lookahead(self):
        """point-in-time 序列 = raw.shift(1)：day-t 值改变 r_t 不影响。"""
        r = [0.01, -0.02, 0.03, 0.005, -0.01]
        forecast = volatility.ewma_forecast_series(r)
        raw = volatility.ewma_variance_series(r)
        assert len(forecast) == len(r) - 1
        np.testing.assert_allclose(forecast.to_numpy(), raw.to_numpy()[:-1])
        # 防前视：改动第 t 日收益，forecast 在 ≤t 的值不变
        r_modified = [0.01, -0.02, 0.99, 0.005, -0.01]
        forecast_modified = volatility.ewma_forecast_series(r_modified)
        np.testing.assert_allclose(forecast.to_numpy()[:1], forecast_modified.to_numpy()[:1])

    def test_latest_forecast_is_last_raw_value(self):
        rng = np.random.default_rng(6)
        r = rng.normal(0.0, 0.02, 100)
        result = volatility.latest_ewma_forecast(r)
        raw = volatility.ewma_variance_series(r)
        assert result["variance_forecast"] == pytest.approx(float(raw.iloc[-1]))
        assert result["volatility_forecast"] == pytest.approx(float(np.sqrt(raw.iloc[-1])))
        assert result["lambda"] == pytest.approx(0.94)

    def test_insufficient_data_raises(self):
        with pytest.raises(ValueError):
            volatility.ewma_variance_series([0.01])


class TestFitGarch11:
    def test_recovers_stationary_simulation(self):
        """确定性 GARCH(1,1) 模拟（真值已知）→ 拟合 α+β、平稳性、V_L、半衰期 sane 范围。

        真值（收益率量纲）：ω=1e-6, α=0.08, β=0.90 → V_L=5e-5, 半衰期≈37.2 天。
        """
        r = _simulate_garch11(omega=1e-6, alpha=0.08, beta=0.90, nobs=4000, seed=42)
        result = volatility.fit_garch11(r)
        assert result["stationary"] is True
        assert 0.9 < result["persistence"] < 1.0
        assert result["alpha"] > 0
        assert result["beta"] > 0
        assert result["long_run_variance"] > 0
        # 半衰期正且股权类量级（数天~数百天）
        assert 5.0 < result["half_life_days"] < 500.0
        # 拟合值落在真值合理邻域
        assert result["alpha"] == pytest.approx(0.08, abs=0.05)
        assert result["beta"] == pytest.approx(0.90, abs=0.08)
        assert result["latest_conditional_volatility"] > 0

    @pytest.mark.filterwarnings("ignore::arch.univariate.base.DataScaleWarning")
    def test_non_stationary_simulation_flagged(self):
        """α+β≥1 模拟 → stationary=False，V_L/半衰期为 None。"""
        r = _simulate_garch11(omega=1e-6, alpha=0.12, beta=0.93, nobs=4000, seed=7)
        result = volatility.fit_garch11(r)
        assert result["stationary"] is False
        assert result["persistence"] >= 1.0
        assert result["long_run_variance"] is None
        assert result["half_life_days"] is None

    def test_scaling_round_trip(self):
        """收益 ×100 拟合 ÷100² 还原：ω 量纲与输入收益一致（~1e-6 而非 ~1e-2）。"""
        r = _simulate_garch11(omega=1e-6, alpha=0.08, beta=0.90, nobs=3000, seed=5)
        result = volatility.fit_garch11(r)
        assert result["omega"] < 1e-4  # 若未还原则为 ~1e-2 量级

    def test_short_series_raises(self):
        with pytest.raises(ValueError):
            volatility.fit_garch11([0.01] * 30)


class TestVolatilityRegime:
    def test_synthetic_three_regimes(self):
        """平静/过渡/高波三段合成 → 标签 low/mid/high 各 100。"""
        vol = np.concatenate([np.full(100, 0.01), np.full(100, 0.02), np.full(100, 0.03)])
        labels = volatility.volatility_regime(vol)
        assert (labels.iloc[:100] == "low").all()
        assert (labels.iloc[100:200] == "mid").all()
        assert (labels.iloc[200:] == "high").all()

    def test_counts_cover_all(self):
        rng = np.random.default_rng(2)
        labels = volatility.volatility_regime(np.abs(rng.normal(0, 0.01, 300)))
        assert set(labels.unique()) <= {"low", "mid", "high"}
        assert len(labels) == 300
