"""risk.barometer 单测：组合收益手算、组合法对接 tail/volatility 集成、
滚动分位 warmup 降级、预警三态、build_barometer 组装。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.risk import barometer, tail, volatility


def _panel(data: dict[str, list[float]]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(next(iter(data.values()))), freq="B")
    return pd.DataFrame(data, index=idx)


class TestPortfolioReturnSeries:
    def test_equal_and_cap_weight_hand_computed(self):
        panel = _panel({"a": [0.02, 0.01], "b": [-0.01, 0.03], "c": [np.nan, 0.0]})
        w = _panel({"a": [0.5, 0.25], "b": [0.25, 0.25], "c": [0.25, 0.5]})
        out = barometer.portfolio_return_series(panel, weights=w)
        # day0 等权 = (0.02 − 0.01)/2 = 0.005（c 为 NaN 剔除）
        assert out["r_equal_weight"].iloc[0] == pytest.approx(0.005)
        # day0 市值加权：权重在有效股 a,b 上归一化 (2/3, 1/3) → 0.02·2/3 − 0.01·1/3
        assert out["r_cap_weight"].iloc[0] == pytest.approx(0.02 * 2 / 3 - 0.01 * 1 / 3)
        # day1 等权 = 0.04/3；市值加权 = 0.25·0.01+0.25·0.03+0.5·0 = 0.01
        assert out["r_equal_weight"].iloc[1] == pytest.approx(0.04 / 3)
        assert out["r_cap_weight"].iloc[1] == pytest.approx(0.01)

    def test_no_weights_only_equal(self):
        out = barometer.portfolio_return_series(_panel({"a": [0.01], "b": [0.03]}))
        assert "r_cap_weight" not in out.columns
        assert out["r_equal_weight"].iloc[0] == pytest.approx(0.02)


class TestPortfolioRiskSummary:
    def test_matches_tail_and_volatility_direct_calls(self):
        """组合法 100% 复用：结果与直接调 tail/volatility 逐键一致。"""
        rng = np.random.default_rng(42)
        r = pd.Series(rng.normal(0, 0.015, 300))
        summary = barometer.portfolio_risk_summary(r)
        ewma = volatility.latest_ewma_forecast(r)
        assert summary["ewma_volatility_forecast"] == pytest.approx(ewma["volatility_forecast"])
        for conf in (0.95, 0.99):
            key = f"{int(conf * 100)}pct"
            hist = tail.historical_var_es(r, confidence=conf)
            ewp = tail.ewma_parametric_var_es(r, confidence=conf)
            assert summary["levels"][key]["historical"]["var"] == pytest.approx(hist["var"])
            assert summary["levels"][key]["historical"]["es"] == pytest.approx(hist["es"])
            assert summary["levels"][key]["ewma_parametric"]["var"] == pytest.approx(ewp["var"])
            assert summary["levels"][key]["ewma_parametric"]["es"] == pytest.approx(ewp["es"])


class TestRollingPercentileScore:
    def test_known_scores(self):
        """window=4，序列 [1,2,3,4,5,1]：t=3 时窗口 [1,2,3,4]，x=4 → 100；
        t=5 时窗口 [3,4,5,1]，x=1 → 25。"""
        out = barometer.rolling_percentile_score(pd.Series([1.0, 2, 3, 4, 5, 1]), window=4)
        assert out["warmup"].tolist() == [True, True, True, False, False, False]
        assert out["score"].iloc[3] == pytest.approx(100.0)
        assert out["score"].iloc[4] == pytest.approx(100.0)
        assert out["score"].iloc[5] == pytest.approx(25.0)

    def test_warmup_degrades_to_none_not_fake(self):
        """历史不足 → NaN + warmup=True（不伪造分数）。"""
        out = barometer.rolling_percentile_score(pd.Series([1.0, 2.0]), window=252)
        assert out["warmup"].all()
        assert out["score"].isna().all()


class TestEvaluateAlert:
    def test_green_when_neither_exceeds(self):
        corr = pd.Series(np.linspace(0.2, 0.25, 60))  # 20 日升幅 ≈ 0.017 < 0.10
        breach = pd.Series([0.005] * 60)
        out = barometer.evaluate_alert(corr, breach)
        assert out["alert"] == "green"
        assert out["corr_exceed"] is False and out["breach_exceed"] is False

    def test_amber_on_single_exceed(self):
        corr = pd.Series([0.2] * 40 + list(np.linspace(0.2, 0.35, 21)))  # 升幅 0.15 > 0.10
        breach = pd.Series([0.005] * 61)
        out = barometer.evaluate_alert(corr, breach)
        assert out["alert"] == "amber"
        assert out["corr_exceed"] is True and out["breach_exceed"] is False
        # 反向：仅突破占比超阈
        out2 = barometer.evaluate_alert(pd.Series([0.2] * 61), pd.Series([0.005] * 60 + [0.05]))
        assert out2["alert"] == "amber"
        assert out2["breach_exceed"] is True and out2["corr_exceed"] is False

    def test_red_on_double_exceed(self):
        corr = pd.Series([0.2] * 40 + list(np.linspace(0.2, 0.35, 21)))
        breach = pd.Series([0.005] * 60 + [0.05])  # 末日 5% > 3%
        out = barometer.evaluate_alert(corr, breach)
        assert out["alert"] == "red"
        assert out["corr_change"] == pytest.approx(0.35 - 0.2, abs=1e-9)
        assert out["corr_jump_threshold"] == 0.10
        assert out["breach_ratio_threshold"] == 0.03

    def test_corr_history_insufficient_disclosed(self):
        """相关历史 ≤ lookback → corr 判据不触发（None 披露），不误判 red。"""
        out = barometer.evaluate_alert(pd.Series([0.3] * 10), pd.Series([0.05] * 10), corr_lookback=20)
        assert out["corr_change"] is None
        assert out["corr_exceed"] is False
        assert out["alert"] == "amber"  # 仅突破占比超阈


class TestBuildBarometer:
    def _panel(self, n: int = 80, seed: int = 1) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        data = {f"s{i}": rng.normal(0, 0.02, n).tolist() for i in range(6)}
        return _panel(data)

    def test_structure_market_and_groups(self):
        panel = self._panel()
        groups = {"grp_ab": ["s0", "s1", "s2"], "grp_small": ["s0"], "grp_missing": ["x", "y"]}
        out = barometer.build_barometer(panel, groups=groups, score_window=30)
        assert set(out["market"]["scores_latest"]) == set(barometer.SCORE_COMPONENTS)
        assert "grp_ab" in out["groups"]
        # <2 只成员或面板中不存在的组跳过并披露
        assert set(out["skipped_groups"]) == {"grp_small", "grp_missing"}
        for section in (out["market"], out["groups"]["grp_ab"]):
            assert section["alert"]["alert"] in {"green", "amber", "red"}
            assert set(section["portfolio"]) == {"equal_weight"}

    def test_warmup_propagates_to_total_score(self):
        """score_window 大于历史 → 全部 warmup → total_score None。"""
        panel = self._panel(n=40)
        out = barometer.build_barometer(panel, score_window=252)
        assert out["market"]["warmup"] is True
        assert out["market"]["total_score"] is None
        assert all(v is None for v in out["market"]["scores_latest"].values())

    def test_scores_in_range_when_history_sufficient(self):
        panel = self._panel(n=80)
        out = barometer.build_barometer(panel, score_window=30)
        scores = out["market"]["scores_latest"]
        for v in scores.values():
            assert v is None or 0.0 <= v <= 100.0

    def test_equal_vs_cap_weight_differ(self):
        """等权与市值加权组合序列在倾斜权重下不同（差异用例）。"""
        panel = self._panel()
        w = panel.copy()
        w.iloc[:] = 0.01
        w["s0"] = 0.95  # 权重压向 s0
        out = barometer.build_barometer(panel, weights=w, score_window=30)
        port = out["market"]["portfolio_series"]
        assert set(out["market"]["portfolio"]) == {"equal_weight", "cap_weight"}
        diff = (port["r_equal_weight"] - port["r_cap_weight"]).abs().max()
        assert diff > 1e-6

    def test_constants_echoed(self):
        out = barometer.build_barometer(self._panel(n=70), score_window=30)
        assert out["market"]["cross_section_params"]["corr_window"] == 60
        assert out["market"]["alert"]["corr_jump_threshold"] == 0.10
        assert out["market"]["alert"]["breach_ratio_threshold"] == 0.03
