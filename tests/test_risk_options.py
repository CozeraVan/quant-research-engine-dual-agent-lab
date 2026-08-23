"""risk.options 单测：教材例题解析值 + 手算核对 + 自检恒等式（PDE/parity/收敛）。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from quant_research_engine.risk import options
from quant_research_engine.risk.constants import (
    DEFAULT_TREE_STEPS,
    GREEK_SHOCK_RATE,
    GREEK_SHOCK_SIGMA,
    IV_BRACKET,
)

#: 书4 Ch15 教材解析例参数（摘要 p776）：d1=0.2001, d2=−0.1674, c=8.3069, p=7.9715
BSM_EX = dict(S0=56.0, K=60.0, r=0.05, sigma=0.30, T=1.5)

#: 书4 Ch14 美式 put 例（教材原文 Figure 14.5/14.6，S=29, K=30, r=3%, σ=25%, T=1）：
#: 2 步美式=3.058（节点 B=0.494、C=5.699 提前行权）、欧式=2.838、4 步=3.097、
#: 20/50/100/500 步=3.082/3.067/3.059/3.055
TREE_EX = dict(S0=29.0, K=30.0, r=0.03, sigma=0.25, T=1.0)


class TestBsmPrice:
    def test_textbook_example_ch15(self):
        """书4 Ch15 式 15.6/15.7 数值例：S=56,K=60,r=5%,σ=30%,T=1.5
        → d1=0.2001, d2=−0.1674, c=8.3069, p=7.9715（CR §4 R6 验收点）。"""
        c = options.bsm_price(**BSM_EX, option_type="call")
        p = options.bsm_price(**BSM_EX, option_type="put")
        assert c["d1"] == pytest.approx(0.2001, abs=5e-5)
        assert c["d2"] == pytest.approx(-0.1674, abs=5e-5)
        assert c["price"] == pytest.approx(8.3069, abs=5e-4)
        assert p["price"] == pytest.approx(7.9715, abs=5e-4)

    def test_put_call_parity(self):
        """Put-call parity 自检（式 14.1 变形/13.4）：c − p = S₀ − K·e^{−rT}。"""
        c = options.bsm_price(**BSM_EX, option_type="call")["price"]
        p = options.bsm_price(**BSM_EX, option_type="put")["price"]
        lhs = c - p
        rhs = BSM_EX["S0"] - BSM_EX["K"] * math.exp(-BSM_EX["r"] * BSM_EX["T"])
        assert lhs == pytest.approx(rhs, abs=1e-10)

    def test_continuous_dividend_lowers_call(self):
        """式 15.8/15.9：q>0 时 call 降价、put 升价；q=0 退化为无股息。"""
        c0 = options.bsm_price(50, 50, 0.05, 0.3, 1.0, q=0.0)["price"]
        cq = options.bsm_price(50, 50, 0.05, 0.3, 1.0, q=0.03)["price"]
        p0 = options.bsm_price(50, 50, 0.05, 0.3, 1.0, q=0.0, option_type="put")["price"]
        pq = options.bsm_price(50, 50, 0.05, 0.3, 1.0, q=0.03, option_type="put")["price"]
        assert cq < c0 and pq > p0

    def test_discrete_dividend_adjustment(self):
        """离散股息修正（书4 Ch15）：dividend_pv=D ≡ 以 S₀−D 直接调用。"""
        d_pv = 2.0
        adj = options.bsm_price(56, 60, 0.05, 0.30, 1.5, dividend_pv=d_pv)
        direct = options.bsm_price(56 - d_pv, 60, 0.05, 0.30, 1.5)
        assert adj["price"] == pytest.approx(direct["price"], abs=1e-12)
        assert adj["d1"] == pytest.approx(direct["d1"], abs=1e-12)

    def test_validation(self):
        with pytest.raises(ValueError):
            options.bsm_price(-1, 60, 0.05, 0.3, 1.5)
        with pytest.raises(ValueError):
            options.bsm_price(56, 60, 0.05, -0.3, 1.5)
        with pytest.raises(ValueError):
            options.bsm_price(56, 60, 0.05, 0.3, 1.5, option_type="straddle")
        with pytest.raises(ValueError):
            options.bsm_price(56, 60, 0.05, 0.3, 1.5, dividend_pv=100.0)


class TestBlack76:
    def test_equivalence_with_bsm(self):
        """书4 Ch15：同 K 同 T 期货期权与现货期权等价（F₀ = S₀e^{(r−q)T}）。"""
        S0, K, r, q, sigma, T = 100.0, 105.0, 0.05, 0.03, 0.25, 1.0
        f0 = S0 * math.exp((r - q) * T)
        for ot in ("call", "put"):
            black = options.black76_price(f0, K, r, sigma, T, option_type=ot)["price"]
            bsm = options.bsm_price(S0, K, r, sigma, T, q=q, option_type=ot)["price"]
            assert black == pytest.approx(bsm, abs=1e-10)

    def test_parity(self):
        """期货期权 parity：c − p = e^{−rT}(F₀ − K)。"""
        F0, K, r, sigma, T = 60.0, 62.0, 0.05, 0.2, 0.5
        c = options.black76_price(F0, K, r, sigma, T, "call")["price"]
        p = options.black76_price(F0, K, r, sigma, T, "put")["price"]
        assert c - p == pytest.approx(math.exp(-r * T) * (F0 - K), abs=1e-10)


class TestImpliedVol:
    def test_textbook_example(self):
        """书4 Ch15 教材例：同 BSM_EX 参数的 call 市价 7.00 → σ≈25.14%
        （CR §4 R6 验收点）。"""
        result = options.implied_vol(7.00, 56, 60, 0.05, 1.5, option_type="call")
        assert result["method"] == "brentq"
        assert result["implied_vol"] == pytest.approx(0.2514, abs=5e-4)

    def test_roundtrip(self):
        """定价→反解往返：任意 σ 输入反解回原值。"""
        target = 0.42
        price = options.bsm_price(100, 95, 0.02, target, 0.75, q=0.01, option_type="put")["price"]
        result = options.implied_vol(price, 100, 95, 0.02, 0.75, option_type="put", q=0.01)
        assert result["implied_vol"] == pytest.approx(target, abs=1e-10)
        assert result["bracket"] == IV_BRACKET

    def test_not_bracketed_rejected(self):
        """价格低于内在价值下界 → 不在 bracket 内报错。"""
        with pytest.raises(ValueError):
            options.implied_vol(0.001, 56, 60, 0.05, 1.5, option_type="call")


class TestCrrTree:
    def test_american_put_textbook_nodes(self):
        """书4 Ch14 Figure 14.5 美式 put 节点值（CR §4 验收点）：
        A=3.058，B（上）=0.494 不行权，C（下）=5.699 提前行权；
        欧式=2.838；美式溢价=0.22。"""
        am = options.crr_tree(**TREE_EX, n_steps=2, option_type="put",
                              american=True, return_grid=True)
        assert am["price"] == pytest.approx(3.058, abs=5e-4)
        grid = am["grid"]
        # grid[step][j]，j=上涨次数：第一层 j=1 为节点 B（上）、j=0 为节点 C（下）
        assert float(grid[1][1]) == pytest.approx(0.494, abs=5e-4)
        assert float(grid[1][0]) == pytest.approx(5.699, abs=5e-4)
        # 提前行权标记：仅节点 C
        ex = am["exercise_grid"]
        assert bool(ex[1][0]) is True and bool(ex[1][1]) is False
        eu = options.crr_tree(**TREE_EX, n_steps=2, option_type="put", american=False)
        assert eu["price"] == pytest.approx(2.838, abs=5e-4)
        assert am["price"] - eu["price"] == pytest.approx(0.22, abs=1e-3)
        # 末端节点 payoff 手算：S=29·d²=20.30 → put 9.637；S=29 → 1.0；S=29·u² → 0
        assert float(grid[2][0]) == pytest.approx(9.637, abs=5e-4)
        assert float(grid[2][1]) == pytest.approx(1.0, abs=1e-9)
        assert float(grid[2][2]) == pytest.approx(0.0, abs=1e-12)

    def test_convergence_steps(self):
        """书4 Ch14 收敛例（CR §4 验收点）：美式 put
        4 步=3.097；20/50/100/500 步 → 3.082/3.067/3.059/3.055。"""
        expected = {4: 3.097, 20: 3.082, 50: 3.067, 100: 3.059, 500: 3.055}
        for n, val in expected.items():
            price = options.crr_tree(**TREE_EX, n_steps=n, option_type="put",
                                     american=True)["price"]
            assert price == pytest.approx(val, abs=5e-4), f"n_steps={n}"

    def test_european_tree_converges_to_bsm(self):
        """书4 Ch14：步数↑欧式树收敛到 BSM（同一随机游走假设）。
        CRR 收敛速度 O(1/n) 且振荡，500 步容差 abs 3e-3。"""
        bsm = options.bsm_price(56, 60, 0.05, 0.30, 1.5, option_type="call")["price"]
        tree = options.crr_tree(56, 60, 0.05, 0.30, 1.5, n_steps=500, option_type="call")
        assert tree["price"] == pytest.approx(bsm, abs=3e-3)

    def test_tree_ud_pq_formulas(self):
        """式 14.6/14.7：u=e^{σ√Δt}、d=1/u、p=(e^{(r−q)Δt}−d)/(u−d) 手算核对。"""
        n = 4
        t = options.crr_tree(**TREE_EX, n_steps=n, option_type="put", american=True)
        dt = 1.0 / n
        assert t["u"] == pytest.approx(math.exp(0.25 * math.sqrt(dt)), abs=1e-12)
        assert t["d"] == pytest.approx(math.exp(-0.25 * math.sqrt(dt)), abs=1e-12)
        assert t["p"] == pytest.approx(
            (math.exp(0.03 * dt) - t["d"]) / (t["u"] - t["d"]), abs=1e-12
        )
        assert t["p"] == pytest.approx(0.4988, abs=5e-5)  # 教材 Figure 14.6 值

    def test_first_layer_delta(self):
        """式 14.1：树第一层 delta = (f_u − f_d)/(S₀u − S₀d)，与美式 put
        教材第一层值核对：(0.494 − 5.699)/(29u − 29d)。"""
        t = options.crr_tree(**TREE_EX, n_steps=2, option_type="put",
                             american=True, return_grid=True)
        f_u, f_d = float(t["grid"][1][1]), float(t["grid"][1][0])
        expected = (f_u - f_d) / (29.0 * t["u"] - 29.0 * t["d"])
        assert t["delta"] == pytest.approx(expected, abs=1e-12)
        assert t["delta"] == pytest.approx((0.494 - 5.699) / (29.0 * (t["u"] - t["d"])), abs=5e-4)

    def test_american_no_early_exercise_call_equals_european(self):
        """书3 Ch13：无股息美式 call 不应提前行权 → 美式价=欧式价。"""
        am = options.crr_tree(50, 50, 0.05, 0.3, 1.0, n_steps=50, option_type="call",
                              american=True)
        eu = options.crr_tree(50, 50, 0.05, 0.3, 1.0, n_steps=50, option_type="call",
                              american=False)
        assert am["price"] == pytest.approx(eu["price"], abs=1e-12)

    def test_dividend_yield_tree(self):
        """含 q 树（式 14.7）：欧式含 q 树收敛到含 q BSM
        （CRR O(1/n) 振荡收敛，1000 步容差 abs 3e-3）。"""
        bsm = options.bsm_price(100, 100, 0.05, 0.25, 1.0, q=0.04, option_type="put")["price"]
        tree = options.crr_tree(100, 100, 0.05, 0.25, 1.0, n_steps=1000, q=0.04,
                                option_type="put")
        assert tree["price"] == pytest.approx(bsm, abs=3e-3)

    def test_validation(self):
        with pytest.raises(ValueError):
            options.crr_tree(29, 30, 0.03, 0.25, 1.0, n_steps=1)
        with pytest.raises(ValueError):
            options.crr_tree(29, 30, 0.03, 0.25, 1.0, option_type="straddle")


class TestGreeks:
    def test_bsm_pde_identity(self):
        """BSM PDE 自检恒等式（式 16.2，CR §4 验收点）：
        θ + rSΔ + ½σ²S²Γ = rf（call/put 均成立）。"""
        for ot in ("call", "put"):
            g = options.bsm_greeks(**BSM_EX, option_type=ot)
            f = options.bsm_price(**BSM_EX, option_type=ot)["price"]
            lhs = (g["theta"] + BSM_EX["r"] * BSM_EX["S0"] * g["delta"]
                   + 0.5 * BSM_EX["sigma"] ** 2 * BSM_EX["S0"] ** 2 * g["gamma"])
            assert lhs == pytest.approx(BSM_EX["r"] * f, abs=1e-10)

    def test_bsm_pde_identity_with_dividend(self):
        """含 q 版 PDE（Table 16.2）：θ + (r−q)SΔ + ½σ²S²Γ = rf。"""
        S0, K, r, q, sigma, T = 50.0, 50.0, 0.05, 0.02, 0.3, 1.0
        for ot in ("call", "put"):
            g = options.bsm_greeks(S0, K, r, sigma, T, q=q, option_type=ot)
            f = options.bsm_price(S0, K, r, sigma, T, q=q, option_type=ot)["price"]
            lhs = g["theta"] + (r - q) * S0 * g["delta"] + 0.5 * sigma**2 * S0**2 * g["gamma"]
            assert lhs == pytest.approx(r * f, abs=1e-10)

    def test_greeks_match_finite_difference(self):
        """解析 Greeks 对 bsm_price 中心差分（含 q，五值全核对）。"""
        S0, K, r, q, sigma, T = 50.0, 50.0, 0.05, 0.02, 0.3, 1.0
        h = 1e-5
        for ot in ("call", "put"):
            g = options.bsm_greeks(S0, K, r, sigma, T, q=q, option_type=ot)
            f = lambda **kw: options.bsm_price(  # noqa: E731
                kw.get("S0", S0), K, kw.get("r", r), kw.get("sigma", sigma),
                kw.get("T", T), q=q, option_type=ot)["price"]
            assert g["delta"] == pytest.approx((f(S0=S0 + h) - f(S0=S0 - h)) / (2 * h), rel=1e-5)
            assert g["vega"] == pytest.approx((f(sigma=sigma + h) - f(sigma=sigma - h)) / (2 * h), rel=1e-6)
            assert g["theta"] == pytest.approx((f(T=T - h) - f(T=T + h)) / (2 * h), rel=1e-5)
            assert g["rho"] == pytest.approx((f(r=r + h) - f(r=r - h)) / (2 * h), rel=1e-5)

    def test_gamma_vega_call_put_equal(self):
        """书4 Ch16：gamma/vega call 与 put 相同。"""
        g_c = options.bsm_greeks(50, 50, 0.05, 0.3, 1.0, option_type="call")
        g_p = options.bsm_greeks(50, 50, 0.05, 0.3, 1.0, option_type="put")
        assert g_c["gamma"] == pytest.approx(g_p["gamma"], abs=1e-12)
        assert g_c["vega"] == pytest.approx(g_p["vega"], abs=1e-12)

    def test_delta_bounds_and_put_delta(self):
        """式 16.1/Table 16.2：Δc = e^{−qT}N(d1) ∈ (0,1)；Δp = Δc − e^{−qT}。"""
        g_c = options.bsm_greeks(50, 50, 0.05, 0.3, 1.0, q=0.02, option_type="call")
        g_p = options.bsm_greeks(50, 50, 0.05, 0.3, 1.0, q=0.02, option_type="put")
        assert 0 < g_c["delta"] < 1
        assert g_p["delta"] == pytest.approx(g_c["delta"] - math.exp(-0.02), abs=1e-12)

    def test_black76_greeks(self):
        """期货期权版 Greeks（Table 16.2）：rho = −f·T；其余对有限差分。"""
        F0, K, r, sigma, T = 60.0, 60.0, 0.05, 0.2, 0.5
        h = 1e-5
        for ot in ("call", "put"):
            g = options.black76_greeks(F0, K, r, sigma, T, option_type=ot)
            f = lambda **kw: options.black76_price(  # noqa: E731
                kw.get("F0", F0), K, kw.get("r", r), kw.get("sigma", sigma),
                kw.get("T", T), option_type=ot)["price"]
            assert g["rho"] == pytest.approx(-g["price"] * T, abs=1e-12)
            assert g["delta"] == pytest.approx((f(F0=F0 + h) - f(F0=F0 - h)) / (2 * h), rel=1e-5)
            assert g["vega"] == pytest.approx((f(sigma=sigma + h) - f(sigma=sigma - h)) / (2 * h), rel=1e-6)
            assert g["theta"] == pytest.approx((f(T=T - h) - f(T=T + h)) / (2 * h), rel=1e-5)
            assert g["rho"] == pytest.approx((f(r=r + h) - f(r=r - h)) / (2 * h), rel=1e-5)

    def test_american_greeks_numeric_vs_bsm_on_european_call(self):
        """书4 Ch16 美式数值差分：无股息美式 call 不提前行权，
        200 步树的数值 Greeks 应逼近 BSM 解析值。"""
        ag = options.american_greeks_numeric(56, 60, 0.05, 0.30, 1.5, n_steps=200,
                                             option_type="call")
        bg = options.bsm_greeks(56, 60, 0.05, 0.30, 1.5, option_type="call")
        assert ag["shock_sigma"] == GREEK_SHOCK_SIGMA
        assert ag["shock_rate"] == GREEK_SHOCK_RATE
        assert ag["delta"] == pytest.approx(bg["delta"], abs=1e-3)
        assert ag["gamma"] == pytest.approx(bg["gamma"], abs=1e-3)
        assert ag["vega"] == pytest.approx(bg["vega"], rel=1e-2)
        assert ag["theta"] == pytest.approx(bg["theta"], rel=2e-2)
        assert ag["rho"] == pytest.approx(bg["rho"], rel=2e-2)

    def test_portfolio_greeks_weighted_sum(self):
        """书4 Ch16：组合 Greeks = Σ 数量×单值（空头为负）。"""
        positions = [
            {"name": "long_call", "quantity": 3.0, "delta": 0.5, "gamma": 0.02,
             "vega": 20.0, "theta": -4.0, "rho": 30.0},
            {"name": "short_put", "quantity": -2.0, "delta": -0.4, "gamma": 0.03,
             "vega": 25.0, "theta": -3.0, "rho": -35.0},
        ]
        result = options.portfolio_greeks(positions)
        assert result["delta"] == pytest.approx(3 * 0.5 + (-2) * (-0.4), abs=1e-12)
        assert result["gamma"] == pytest.approx(3 * 0.02 + (-2) * 0.03, abs=1e-12)
        assert result["vega"] == pytest.approx(3 * 20.0 + (-2) * 25.0, abs=1e-12)
        assert result["theta"] == pytest.approx(3 * (-4.0) + (-2) * (-3.0), abs=1e-12)
        assert result["rho"] == pytest.approx(3 * 30.0 + (-2) * (-35.0), abs=1e-12)
        with pytest.raises(ValueError):
            options.portfolio_greeks([])


class TestConstants:
    def test_r6_constants_echoed(self):
        """R6 集中参数存在且在结果 dict 回显。"""
        assert IV_BRACKET[0] > 0 and IV_BRACKET[1] > 1.0
        assert DEFAULT_TREE_STEPS >= 30  # 书4 Ch14：实务至少 30–50 步
        iv = options.implied_vol(7.00, 56, 60, 0.05, 1.5)
        assert iv["bracket"] == IV_BRACKET
        tree = options.crr_tree(29, 30, 0.03, 0.25, 1.0, option_type="put")
        assert tree["n_steps"] == DEFAULT_TREE_STEPS
