"""risk.report 单测：结构键齐全、参数回显、benchmark=None 降级、可 JSON 序列化。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
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
        assert set(report) == {
            "meta", "distribution", "tail", "volatility", "dependence",
            "performance", "var_backtest",
        }

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


class TestVarBacktestSection:
    def test_default_on_with_ewma_var(self, returns):
        """默认开启；VaR 序列默认 EWMA 预测 σ×z（μ=0 RiskMetrics 口径）。"""
        report = build_risk_report(returns)
        section = report["var_backtest"]
        assert section["enabled"] is True
        assert set(section["levels"]) == {"95pct", "99pct"}
        for entry in section["levels"].values():
            assert "error" not in entry
            assert entry["n_obs"] == 399  # EWMA forecast shift(1) 丢首值
            assert "EWMA" in entry["var_source"]
        assert section["false_positive_warning"]["examples"]["n_tests_10"] == pytest.approx(
            0.401263, abs=1e-6
        )

    def test_explicit_var_series_overrides_default(self, returns):
        """config.var_series 显式传入 → var_source 注明，n_obs 不再减一。"""
        var = np.full(len(returns), 0.10)
        report = build_risk_report(returns, config={"var_series": var})
        entry = report["var_backtest"]["levels"]["99pct"]
        assert entry["n_obs"] == len(returns)
        assert entry["violations"] == 0
        assert "config.var_series" in entry["var_source"]

    def test_disable_via_config(self, returns):
        report = build_risk_report(returns, config={"var_backtest": False})
        assert report["var_backtest"] == {"enabled": False}
        assert report["meta"]["sections"]["var_backtest"] is False


class TestStressSection:
    def test_default_off(self, returns):
        assert "stress" not in build_risk_report(returns)

    def test_non_datetime_index_degrades(self, returns):
        report = build_risk_report(returns, config={"stress": True})
        assert "error" in report["stress"]

    def test_replay_with_datetime_index(self):
        idx = pd.date_range("2018-01-01", periods=250, freq="B")
        rng = np.random.default_rng(6)
        returns = pd.Series(rng.normal(0, 0.01, 250), index=idx)
        benchmark = pd.Series(returns * 0.8 + rng.normal(0, 0.005, 250), index=idx)
        report = build_risk_report(
            returns,
            benchmark,
            config={"stress": True, "reverse_stress_threshold": 0.15},
        )
        section = report["stress"]
        assert "error" not in section["scenarios"]["bear_2018"]
        assert "error" in section["scenarios"]["covid_2020"]  # 样本未覆盖
        assert section["var_es_reference"]["var"] is not None
        reverse = section["reverse_stress"]
        assert "error" not in reverse
        assert reverse["required_market_shock"] > 0

    def test_reverse_stress_requires_benchmark(self):
        idx = pd.date_range("2018-01-01", periods=250, freq="B")
        returns = pd.Series(np.sin(np.arange(250) * 0.1) * 0.01, index=idx)
        report = build_risk_report(
            returns, config={"stress": True, "reverse_stress_threshold": 0.15}
        )
        assert "error" in report["stress"]["reverse_stress"]


class TestBootstrapSection:
    def test_default_off(self, returns):
        assert "bootstrap" not in build_risk_report(returns)

    def test_enabled_structure_and_json(self, returns, benchmark):
        report = build_risk_report(
            returns, benchmark, config={"bootstrap": True, "bootstrap_reps": 100}
        )
        section = report["bootstrap"]
        assert set(section) == {"annualized_return", "sharpe", "max_drawdown"}
        cbb = section["sharpe"]["cbb"]
        assert cbb["n_bootstrap"] == 100
        assert cbb["seed"] == 42  # 默认固定种子（可复现）
        assert cbb["mc_standard_error"] == pytest.approx(
            cbb["bootstrap_std"] / np.sqrt(100), rel=1e-12
        )
        json.dumps(report)


class TestRenderMarkdown:
    """R3：render_risk_markdown 汉化渲染。"""

    def test_sections_and_two_decimals(self):
        from quant_research_engine.risk.report import render_risk_markdown

        idx = pd.date_range("2018-01-01", periods=600, freq="B")
        rng = np.random.default_rng(5)
        returns = pd.Series(rng.standard_t(6, 600) * 0.012, index=idx)
        benchmark = pd.Series(0.6 * returns.to_numpy() + rng.normal(0, 0.008, 600), index=idx)
        report = build_risk_report(returns, benchmark, config={"stress": True})
        md = render_risk_markdown(report)
        assert md.startswith("## 风险分析")
        for header in ("### 分布与尾部", "### VaR 回测", "### 波动率", "### 压力测试", "### 绩效风险指标"):
            assert header in md
        assert "Jarque-Bera" in md
        assert "Sharpe" in md and "Sortino" in md
        # VaR 渲染为百分比两位小数
        import re
        assert re.search(r"\| 99% \| 历史模拟 \| -?\d+\.\d{2}% \| -?\d+\.\d{2}% \|", md)
        # bootstrap 未开启 → 不渲染该区
        assert "Bootstrap" not in md

    def test_error_sections_degrade(self):
        from quant_research_engine.risk.report import render_risk_markdown

        report = build_risk_report([0.01, -0.02, 0.005])  # GARCH 数据不足
        md = render_risk_markdown(report)
        assert "数据不足" in md
        assert "### 压力测试" not in md  # stress 未开启

    def test_bootstrap_section_rendered_when_enabled(self, returns):
        from quant_research_engine.risk.report import render_risk_markdown

        report = build_risk_report(returns, config={"bootstrap": True, "bootstrap_reps": 50})
        md = render_risk_markdown(report)
        assert "### Bootstrap 置信区间（CBB）" in md
        assert "sharpe" in md

    def test_scenario_not_covered_note(self):
        from quant_research_engine.risk.report import render_risk_markdown

        idx = pd.date_range("2025-01-01", periods=120, freq="B")
        returns = pd.Series(np.sin(np.arange(120) * 0.1) * 0.01, index=idx)
        report = build_risk_report(returns, config={"stress": True})
        md = render_risk_markdown(report)
        assert "样本不覆盖该窗口" in md


class TestPortfolioSection:
    """R7 组合层：默认关（向后兼容），显式传入衍生品头寸才追加 portfolio 节。"""

    OPTION_POSITIONS = [
        {"name": "call_a", "quantity": 2.0, "delta": 0.5, "gamma": 0.01, "vega": 10.0, "theta": -2.0, "rho": 3.0},
    ]
    BOND_POSITIONS = [
        {"name": "bond_a", "market_value": 1_000_000.0, "duration": 4.0, "convexity": 20.0, "dv01": 400.0},
    ]

    def test_default_off_backward_compatible(self, returns):
        report = build_risk_report(returns)
        assert "portfolio" not in report
        assert report["meta"]["sections"]["portfolio"] is False

    def test_enabled_with_option_positions(self, returns):
        report = build_risk_report(
            returns,
            config={
                "option_positions": self.OPTION_POSITIONS,
                "dgv": {"spot_shock_sd": 1.5},
            },
        )
        section = report["portfolio"]
        assert "error" not in section
        assert section["meta"]["legs"] == {"equity": True, "fixed_income": False, "options": True}
        assert section["options"]["delta"] == pytest.approx(1.0)
        assert "error" not in section["dgv_var"]
        assert report["meta"]["sections"]["portfolio"] is True
        json.dumps(report)

    def test_enabled_with_bond_positions(self, returns):
        report = build_risk_report(returns, config={"bond_positions": self.BOND_POSITIONS})
        fi = report["portfolio"]["fixed_income"]
        assert fi["dv01"] == pytest.approx(400.0)
        assert fi["duration"] == pytest.approx(4.0)

    def test_bad_positions_degrade_to_error_section(self, returns):
        report = build_risk_report(
            returns,
            config={"bond_positions": [{"market_value": 0.0, "duration": 1.0, "convexity": 1.0, "dv01": 0.0}]},
        )
        assert "error" in report["portfolio"]

    def test_render_markdown_portfolio_section(self, returns):
        from quant_research_engine.risk.report import render_risk_markdown

        report = build_risk_report(
            returns,
            config={
                "bond_positions": self.BOND_POSITIONS,
                "option_positions": self.OPTION_POSITIONS,
                "dgv": {"spot_shock_sd": 1.5},
            },
        )
        md = render_risk_markdown(report)
        assert "### 组合与衍生品风险" in md
        assert "DV01" in md and "Greeks" in md and "DGV" in md

    def test_render_markdown_no_portfolio_by_default(self, returns):
        from quant_research_engine.risk.report import render_risk_markdown

        md = render_risk_markdown(build_risk_report(returns))
        assert "组合与衍生品风险" not in md

    def test_old_format_report_without_portfolio_renders(self, returns):
        """向后兼容：老格式 report dict（无 portfolio 键）渲染不炸。"""
        from quant_research_engine.risk.report import render_risk_markdown

        report = build_risk_report(returns)
        report["meta"].pop("sections", None)  # 模拟 R2 之前的老 meta
        md = render_risk_markdown(report)
        assert md.startswith("## 风险分析")
        assert "组合与衍生品风险" not in md
