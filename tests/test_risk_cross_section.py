"""risk.cross_section 单测：EWMA 面板对单列一致性、已知相关/离散度面板核对、VaR 突破计数。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.risk import cross_section, volatility
from quant_research_engine.risk.constants import EWMA_LAMBDA, Z_99


def _panel(data: dict[str, list[float]]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(next(iter(data.values()))), freq="B")
    return pd.DataFrame(data, index=idx)


class TestEwmaVariancePanel:
    def test_matches_single_column_recursion(self):
        """面板逐列结果 = volatility.ewma_variance_series 单列结果（口径一致性）。"""
        rng = np.random.default_rng(7)
        data = {c: rng.normal(0, 0.02, 50).tolist() for c in ["a", "b", "c"]}
        panel = _panel(data)
        var_panel = cross_section.ewma_variance_panel(panel)
        for c in panel.columns:
            single = volatility.ewma_variance_series(panel[c])
            assert np.allclose(var_panel[c].to_numpy(), single.to_numpy(), atol=1e-15)

    def test_nan_skipped_like_dropna(self):
        """NaN 观测跳过、方差顺延，等价于逐列 dropna 后递推。"""
        r = [0.01, np.nan, -0.02, 0.03]
        panel = _panel({"a": r, "b": [0.02, 0.01, -0.01, 0.005]})
        var_panel = cross_section.ewma_variance_panel(panel)
        single = volatility.ewma_variance_series(pd.Series(r).dropna())
        # day0 初始化 r1²；day1 NaN 顺延；day2/3 继续递推
        assert var_panel["a"].iloc[0] == pytest.approx(0.01**2)
        assert var_panel["a"].iloc[1] == pytest.approx(0.01**2)
        assert var_panel["a"].iloc[2] == pytest.approx(single.iloc[1])
        assert var_panel["a"].iloc[3] == pytest.approx(single.iloc[2])

    def test_hand_computed_two_steps(self):
        """手算：r=[0.01,−0.02]，λ=0.94 → σ²=[1e-4, 1.18e-4]。"""
        panel = _panel({"a": [0.01, -0.02], "b": [0.0, 0.0]})
        var_panel = cross_section.ewma_variance_panel(panel)
        assert var_panel["a"].tolist() == pytest.approx([1e-4, 1.18e-4])
        assert var_panel["b"].tolist() == pytest.approx([0.0, 0.0])

    def test_bad_lambda_raises(self):
        with pytest.raises(ValueError):
            cross_section.ewma_variance_panel(_panel({"a": [0.01, 0.02]}), lam=1.5)


class TestVolatilityStats:
    def test_median_and_quantile_hand_computed(self):
        sig = _panel({"a": [0.01], "b": [0.02], "c": [0.03], "d": [0.04], "e": [np.nan]})
        stats = cross_section.cross_sectional_volatility_stats(sig, quantile=0.9)
        row = stats.iloc[0]
        assert row["median_sigma"] == pytest.approx(0.025)
        # numpy linear 插值：[0.01,0.02,0.03,0.04] q0.9 = 0.037
        assert row["q_high_sigma"] == pytest.approx(0.037)
        assert row["n_stocks"] == 4
        assert stats.attrs["quantile"] == 0.9


class TestDispersion:
    def test_equal_weight_hand_computed(self):
        """[0.01, 0.03] 的 ddof=1 标准差 = 0.014142..."""
        panel = _panel({"a": [0.01], "b": [0.03], "c": [np.nan]})
        out = cross_section.cross_sectional_dispersion(panel)
        assert out["dispersion_equal_weight"].iloc[0] == pytest.approx(np.std([0.01, 0.03], ddof=1))
        assert out["n_stocks"].iloc[0] == 2

    def test_cap_weight_differs_from_equal_weight(self):
        """权重向极端收益倾斜时，加权离散度 < 等权离散度（构造已知方向）。"""
        # 三只收益 −0.05 / 0 / +0.05；权重全压中间 → 加权离散度 ≈ 0
        panel = _panel({"a": [-0.05], "b": [0.0], "c": [0.05]})
        w = _panel({"a": [0.01], "b": [0.98], "c": [0.01]})
        out = cross_section.cross_sectional_dispersion(panel, weights=w)
        ew = out["dispersion_equal_weight"].iloc[0]
        cw = out["dispersion_cap_weight"].iloc[0]
        assert ew == pytest.approx(np.std([-0.05, 0.0, 0.05], ddof=1))
        assert 0 <= cw < ew / 5
        # 手算加权：μ_w = 0.01·(−0.05)+0.98·0+0.01·0.05 = 0
        # σ_w² = 0.01·0.05² + 0.01·0.05² = 5e-5
        assert cw == pytest.approx(np.sqrt(5e-5))

    def test_single_stock_gives_nan(self):
        panel = _panel({"a": [0.01], "b": [np.nan]})
        out = cross_section.cross_sectional_dispersion(panel)
        assert np.isnan(out["dispersion_equal_weight"].iloc[0])


class TestAveragePairwiseCorr:
    def test_perfectly_correlated_panel(self):
        """两只完全同相收益 → 平均相关 = 1；反相 = −1。"""
        rng = np.random.default_rng(3)
        base = rng.normal(0, 0.01, 30)
        panel = _panel({"a": base.tolist(), "b": (2 * base).tolist(), "c": (-base).tolist()})
        out = cross_section.average_pairwise_correlation(panel, window=20)
        last = out["avg_pairwise_corr_equal_weight"].iloc[-1]
        # 三对：+1, −1, −1 → 均值 −1/3
        assert last == pytest.approx(-1.0 / 3.0)
        assert out["n_stocks"].iloc[-1] == 3

    def test_known_two_stock_correlation(self):
        """两只股票 = 唯一一对，均值即两者 Pearson 相关（窗口内完整观测）。"""
        rng = np.random.default_rng(11)
        x = rng.normal(0, 0.02, 60)
        y = 0.5 * x + rng.normal(0, 0.01, 60)
        panel = _panel({"a": x.tolist(), "b": y.tolist()})
        out = cross_section.average_pairwise_correlation(panel, window=60)
        expected = np.corrcoef(x, y)[0, 1]
        assert out["avg_pairwise_corr_equal_weight"].iloc[-1] == pytest.approx(expected, abs=1e-12)

    def test_warmup_window_nan(self):
        panel = _panel({"a": [0.01] * 10, "b": [0.02] * 10})
        out = cross_section.average_pairwise_correlation(panel, window=60)
        assert out["avg_pairwise_corr_equal_weight"].isna().all()

    def test_cap_weight_pair_weighting(self):
        """偶权 w_i·w_j：权重集中于高相关对 → 加权均值高于等权均值。"""
        rng = np.random.default_rng(5)
        base = rng.normal(0, 0.01, 60)
        indep = rng.normal(0, 0.01, 60)
        # a、b 完全相关（+1），c 独立
        panel = _panel({"a": base.tolist(), "b": base.tolist(), "c": indep.tolist()})
        w = _panel({"a": [0.45] * 60, "b": [0.45] * 60, "c": [0.10] * 60})
        out = cross_section.average_pairwise_correlation(panel, window=60, weights=w)
        ew = out["avg_pairwise_corr_equal_weight"].iloc[-1]
        cw = out["avg_pairwise_corr_cap_weight"].iloc[-1]
        assert cw > ew  # 高相关对 (a,b) 偶权 0.2025 占主导

    def test_incomplete_column_excluded(self):
        """窗口内含 NaN 的个股当日剔除，不参与相关均值。"""
        rng = np.random.default_rng(9)
        a = rng.normal(0, 0.01, 30)
        b = a.copy()
        c = rng.normal(0, 0.01, 30)
        c[25] = np.nan  # NaN 落在最后一个窗口（rows 10..29）内
        panel = _panel({"a": a.tolist(), "b": b.tolist(), "c": c.tolist()})
        out = cross_section.average_pairwise_correlation(panel, window=20)
        assert out["n_stocks"].iloc[-1] == 2
        assert out["avg_pairwise_corr_equal_weight"].iloc[-1] == pytest.approx(1.0)


class TestVarBreachRatio:
    def test_hand_computed_count(self):
        """r < −VaR 严格小于才算突破；NaN 剔除。"""
        returns = _panel({"a": [-0.05], "b": [-0.01], "c": [-0.03], "d": [np.nan]})
        var = _panel({"a": [0.03], "b": [0.03], "c": [0.03], "d": [0.03]})
        out = cross_section.var_breach_ratio_series(returns, var, confidence=0.99)
        row = out.iloc[0]
        assert row["breaches"] == 1  # 只有 a（−0.05 < −0.03）
        assert row["n_stocks"] == 3
        assert row["breach_ratio"] == pytest.approx(1 / 3)
        assert out.attrs["confidence"] == 0.99

    def test_boundary_not_breach(self):
        """r == −VaR 不算突破（同 backtest_var.hit_series 严格口径）。"""
        returns = _panel({"a": [-0.03], "b": [-0.031]})
        var = _panel({"a": [0.03], "b": [0.03]})
        out = cross_section.var_breach_ratio_series(returns, var)
        assert out["breaches"].iloc[0] == 1


class TestCrossSectionalSummary:
    def test_integration_ewma_breach_uses_shift(self):
        """summary 的 VaR 突破用 shift(1) 预测：构造恒定 σ 面板核对 VaR=σ·z99。"""
        rng = np.random.default_rng(21)
        panel = _panel({c: rng.normal(0, 0.02, 80).tolist() for c in ["a", "b", "c", "d"]})
        summary = cross_section.cross_sectional_summary(panel)
        assert summary["params"]["lambda"] == EWMA_LAMBDA
        assert summary["params"]["corr_window"] == 60
        # 手工重算末日突破：σ_forecast = sqrt(EWMA raw).shift(1)，VaR = z99·σ
        sigma = np.sqrt(cross_section.ewma_variance_panel(panel)).shift(1)
        expected_breaches = int((panel.iloc[-1] < -Z_99 * sigma.iloc[-1]).sum())
        assert summary["sections"]["var_breach"]["breaches"].iloc[-1] == expected_breaches
