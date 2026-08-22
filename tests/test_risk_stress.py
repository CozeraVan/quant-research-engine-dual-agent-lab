"""risk.stress 单测：情景回放手算、相关性崩溃方向、reverse stress 手算。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.risk import stress
from quant_research_engine.risk.constants import HISTORICAL_SCENARIOS


@pytest.fixture()
def idx():
    return pd.date_range("2015-06-01", periods=10, freq="B")


class TestScenarioLibrary:
    def test_four_ashare_scenarios(self):
        assert set(HISTORICAL_SCENARIOS) == {
            "crash_2015", "bear_2018", "covid_2020", "microcap_liquidity_2024",
        }
        listing = stress.list_scenarios()
        assert listing["crash_2015"]["start"] == "2015-06-15"
        assert listing["microcap_liquidity_2024"]["end"] == "2024-02-29"


class TestReplayScenario:
    def test_hand_computed_cumulative_and_drawdown(self, idx):
        """窗口 2015-06-03~2015-06-08（4 个交易日），r = [−0.10, 0.02, −0.05, 0.01]：
        累计 = 0.9·1.02·0.95·1.01 − 1 = −0.119179；
        净值 0.9/0.918/0.8721/0.880821，峰 0.918 → 峰谷 = 1−0.8721/0.918 = 0.05。"""
        returns = pd.Series([0.01, 0.01, -0.10, 0.02, -0.05, 0.01, 0.0, 0.0, 0.0, 0.0], index=idx)
        result = stress.replay_scenario(returns, ("2015-06-03", "2015-06-08"), var=0.02, es=0.03)
        assert result["n_days"] == 4
        assert result["strategy_cumulative_return"] == pytest.approx(-0.119179, abs=1e-9)
        assert result["strategy_cumulative_loss"] == pytest.approx(0.119179, abs=1e-9)
        assert result["strategy_peak_trough_drawdown"] == pytest.approx(0.05, abs=1e-12)
        assert result["peak_to_var"] == pytest.approx(2.5)
        assert result["peak_to_es"] == pytest.approx(0.05 / 0.03)

    def test_var_es_none_gives_null_ratios(self, idx):
        returns = pd.Series(-0.01, index=idx)
        result = stress.replay_scenario(returns, ("2015-06-01", "2015-06-30"))
        assert result["peak_to_var"] is None
        assert result["peak_to_es"] is None

    def test_window_without_data_raises(self, idx):
        returns = pd.Series(0.01, index=idx)
        with pytest.raises(ValueError):
            stress.replay_scenario(returns, ("2020-01-01", "2020-03-31"))

    def test_correlation_breakdown_direction(self):
        """窗口内策略=基准（corr≈1），窗口外独立（corr≈0）→ delta > 0、elevated。"""
        rng = np.random.default_rng(5)
        idx = pd.date_range("2018-01-01", periods=200, freq="B")
        window = ("2018-03-01", "2018-04-30")
        b = pd.Series(rng.normal(0, 0.01, 200), index=idx)
        r = pd.Series(rng.normal(0, 0.01, 200), index=idx)
        mask = (idx >= window[0]) & (idx <= window[1])
        r.loc[mask] = b.loc[mask] * 1.2  # 窗口内完全联动
        result = stress.replay_scenario(r, window, b)
        cb = result["correlation_breakdown"]
        assert cb["corr_in_window"] == pytest.approx(1.0, abs=1e-9)
        assert cb["delta"] > 0.0
        assert cb["elevated"] is True
        assert result["benchmark_cumulative_return"] is not None


class TestReplayHistoricalScenarios:
    def test_covers_and_degrades(self):
        """样本只覆盖 2018 → 2018 回放成功，其余记 error 不抛异常。"""
        idx = pd.date_range("2018-01-01", periods=250, freq="B")
        returns = pd.Series(np.sin(np.arange(250)) * 0.01, index=idx)
        out = stress.replay_historical_scenarios(returns)
        assert "error" not in out["bear_2018"]
        assert "error" in out["crash_2015"]
        assert "error" in out["covid_2020"]
        assert "error" in out["microcap_liquidity_2024"]


class TestReverseStress:
    def test_hand_computed_linear_passthrough(self):
        """r = 2·b（β=2 精确）；阈值 0.20 → S* = 0.10。
        基准：10 天 −5% 后 90 天 +0.1%；h=5 滚动窗口中全 −5% 段
        累计 = 0.95^5 − 1 = −0.22622 ≤ −0.10 → 分位 > 0。"""
        b = pd.Series([-0.05] * 10 + [0.001] * 90, index=pd.date_range("2023-01-02", periods=100, freq="B"))
        r = 2.0 * b
        result = stress.reverse_stress(r, b, loss_threshold=0.20, horizon=5)
        assert result["beta"] == pytest.approx(2.0, abs=1e-12)
        assert result["required_market_shock"] == pytest.approx(0.10, abs=1e-12)
        rolling = (1.0 + b).rolling(5).apply(np.prod, raw=True) - 1.0
        rolling = rolling.dropna()
        assert (0.95**5 - 1.0) == pytest.approx(-0.226219, abs=1e-6)
        expected_pct = float((rolling <= -0.10).mean())
        assert result["empirical_percentile"] == pytest.approx(expected_pct, rel=1e-12)
        assert result["empirical_percentile"] > 0.0
        assert result["sigma_multiple"] == pytest.approx(0.10 / float(rolling.std(ddof=1)), rel=1e-12)
        assert result["n_rolling_windows"] == 96

    def test_never_seen_shock_gives_zero_percentile(self):
        """所需冲击超过历史最深 → 经验分位 0（bootstrap/历史外推不出黑天鹅）。"""
        rng = np.random.default_rng(1)
        b = pd.Series(rng.normal(0, 0.01, 300), index=pd.date_range("2022-01-03", periods=300, freq="B"))
        r = 0.5 * b  # β=0.5 → 阈值 0.20 → S*=0.40（40% 21 日冲击，远超历史）
        result = stress.reverse_stress(r, b, loss_threshold=0.20, horizon=21)
        assert result["empirical_percentile"] == 0.0

    def test_negative_beta_raises(self):
        """β ≤ 0：市场冲击不构成损失通道 → 报错（需假设性情景）。"""
        idx = pd.date_range("2023-01-02", periods=100, freq="B")
        b = pd.Series(np.sin(np.arange(100) * 0.3) * 0.01, index=idx)
        with pytest.raises(ValueError, match="beta"):
            stress.reverse_stress(-b, b, loss_threshold=0.10)

    def test_bad_threshold_raises(self):
        b = pd.Series(0.001, index=pd.date_range("2023-01-02", periods=10, freq="B"))
        with pytest.raises(ValueError):
            stress.reverse_stress(b, b, loss_threshold=-0.1)
