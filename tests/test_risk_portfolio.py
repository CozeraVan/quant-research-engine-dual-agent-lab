"""risk.portfolio 单测（R7 组合层）：纯股票退化、混合头寸合并、KR01 加总、
DGV-VaR 开关、空输入报错、JSON 可序列化。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.risk.portfolio import summarize_mixed_portfolio


@pytest.fixture()
def returns():
    rng = np.random.default_rng(31)
    return rng.standard_t(6, 400) * 0.012


@pytest.fixture()
def bond_positions():
    return [
        {"name": "bond_a", "market_value": 1_000_000.0, "duration": 4.0, "convexity": 20.0, "dv01": 400.0},
        {"name": "bond_b", "market_value": 3_000_000.0, "duration": 8.0, "convexity": 60.0, "dv01": 2400.0},
    ]


@pytest.fixture()
def option_positions():
    return [
        {"name": "call_a", "quantity": 2.0, "delta": 0.5, "gamma": 0.01, "vega": 10.0, "theta": -2.0, "rho": 3.0},
        {"name": "put_b", "quantity": -1.0, "delta": -0.4, "gamma": 0.02, "vega": 8.0, "theta": -1.0, "rho": -4.0},
    ]


class TestEquityDegradation:
    def test_equity_only(self, returns):
        result = summarize_mixed_portfolio(returns=returns)
        assert result["meta"]["legs"] == {"equity": True, "fixed_income": False, "options": False}
        assert "fixed_income" not in result
        assert "options" not in result
        equity = result["equity"]
        assert equity["n_obs"] == 400
        assert "error" not in equity["performance"]
        assert "sharpe" in equity["performance"]
        ref = equity["var_es_reference"]
        assert "error" not in ref
        assert ref["es"] >= ref["var"]

    def test_equity_with_benchmark(self, returns):
        rng = np.random.default_rng(32)
        benchmark = 0.6 * returns + rng.normal(0, 0.008, len(returns))
        result = summarize_mixed_portfolio(returns=returns, benchmark=benchmark)
        assert result["equity"]["performance"]["beta"] is not None

    def test_no_leg_raises(self):
        with pytest.raises(ValueError, match="至少需要一条腿"):
            summarize_mixed_portfolio()

    def test_empty_lists_treated_absent(self, returns):
        result = summarize_mixed_portfolio(
            returns=returns, bond_positions=[], option_positions=[], bond_kr01=[]
        )
        assert result["meta"]["legs"] == {"equity": True, "fixed_income": False, "options": False}


class TestFixedIncomeLeg:
    def test_portfolio_aggregate_hand_calc(self, bond_positions):
        result = summarize_mixed_portfolio(bond_positions=bond_positions)
        fi = result["fixed_income"]
        assert fi["n_positions"] == 2
        assert fi["total_market_value"] == pytest.approx(4_000_000.0)
        assert fi["dv01"] == pytest.approx(2800.0)  # DV01 可加
        # duration/convexity 市值加权
        assert fi["duration"] == pytest.approx(0.25 * 4.0 + 0.75 * 8.0)
        assert fi["convexity"] == pytest.approx(0.25 * 20.0 + 0.75 * 60.0)
        assert fi["weights"] == pytest.approx([0.25, 0.75])

    def test_kr01_aggregation_matches_single_position(self):
        """KR01 按节点加总：两腿之和 = 合并现金流单独跑一次。"""
        from quant_research_engine.risk import bonds

        curve = {1.0: 0.020, 2.0: 0.025, 3.0: 0.030, 5.0: 0.035, 10.0: 0.040}
        times = [1.0, 2.0, 3.0]
        amounts_a = [30.0, 30.0, 1030.0]
        amounts_b = [25.0, 25.0, 1025.0]
        bond_positions = [
            {"market_value": 1000.0, "duration": 2.0, "convexity": 6.0, "dv01": 0.2},
            {"market_value": 1000.0, "duration": 2.0, "convexity": 6.0, "dv01": 0.2},
        ]
        result = summarize_mixed_portfolio(
            bond_positions=bond_positions,
            bond_kr01=[
                {"name": "a", "times": times, "amounts": amounts_a, "curve": curve},
                {"name": "b", "times": times, "amounts": amounts_b, "curve": curve},
            ],
        )
        kr01 = result["fixed_income"]["kr01"]
        merged = bonds.key_rate_shifts(
            times, [a + b for a, b in zip(amounts_a, amounts_b)], curve
        )
        assert kr01["kr01"] == pytest.approx(list(merged["kr01"]), rel=1e-12)
        # 自检：KR01 之和 ≈ 曲线口径 DV01（一阶恒等式）
        assert kr01["kr01_sum"] == pytest.approx(merged["dv01"], rel=1e-4)

    def test_zero_total_market_value_raises(self):
        with pytest.raises(ValueError):
            summarize_mixed_portfolio(
                bond_positions=[{"market_value": 0.0, "duration": 1.0, "convexity": 1.0, "dv01": 0.0}]
            )


class TestOptionsLeg:
    def test_portfolio_greeks_weighted_sum(self, option_positions):
        result = summarize_mixed_portfolio(option_positions=option_positions)
        opts = result["options"]
        assert opts["n_positions"] == 2
        assert opts["delta"] == pytest.approx(2.0 * 0.5 + (-1.0) * (-0.4))
        assert opts["gamma"] == pytest.approx(2.0 * 0.01 + (-1.0) * 0.02)
        assert opts["vega"] == pytest.approx(2.0 * 10.0 + (-1.0) * 8.0)
        assert opts["theta"] == pytest.approx(2.0 * (-2.0) + (-1.0) * (-1.0))
        assert opts["rho"] == pytest.approx(2.0 * 3.0 + (-1.0) * (-4.0))


class TestDgvVar:
    def test_dgv_computed_when_configured(self, option_positions):
        result = summarize_mixed_portfolio(
            option_positions=option_positions,
            config={"dgv": {"spot_shock_sd": 1.5, "vol_shock_sd": 0.01}},
        )
        dgv = result["dgv_var"]
        assert "error" not in dgv
        assert dgv["delta"] == pytest.approx(result["options"]["delta"])
        assert dgv["var"] > 0
        assert dgv["confidence"] == pytest.approx(0.99)  # 默认取 meta confidence

    def test_dgv_absent_without_config(self, option_positions):
        result = summarize_mixed_portfolio(option_positions=option_positions)
        assert "dgv_var" not in result

    def test_dgv_requires_options_leg(self, returns):
        result = summarize_mixed_portfolio(
            returns=returns, config={"dgv": {"spot_shock_sd": 1.0}}
        )
        assert "error" in result["dgv_var"]

    def test_dgv_invalid_method_raises(self, option_positions):
        with pytest.raises(ValueError, match="method"):
            summarize_mixed_portfolio(
                option_positions=option_positions,
                config={"dgv": {"spot_shock_sd": 1.0, "method": "bogus"}},
            )


class TestMixedPortfolio:
    def test_all_legs_and_json_serializable(self, returns, bond_positions, option_positions):
        result = summarize_mixed_portfolio(
            returns=returns,
            bond_positions=bond_positions,
            option_positions=option_positions,
            config={"dgv": {"spot_shock_sd": 1.5}},
        )
        assert result["meta"]["legs"] == {"equity": True, "fixed_income": True, "options": True}
        assert set(result) == {"meta", "equity", "fixed_income", "options", "dgv_var"}
        json.dumps(result)

    def test_params_echo(self, returns):
        result = summarize_mixed_portfolio(
            returns=returns, config={"risk_free_rate": 0.02, "lam": 0.97}
        )
        assert result["meta"]["risk_free_rate_annual"] == pytest.approx(0.02)
        assert result["meta"]["ewma_lambda"] == pytest.approx(0.97)
        assert result["meta"]["annualization_factor"] == 252
