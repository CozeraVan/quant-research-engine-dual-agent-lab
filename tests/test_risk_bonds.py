"""risk.bonds 单测：教材例题解析值 + 手算核对 + 自检恒等式。"""

from __future__ import annotations

import numpy as np
import pytest

from quant_research_engine.risk import bonds
from quant_research_engine.risk.constants import (
    DEFAULT_DAY_COUNT,
    KEY_RATE_TENORS,
    RATE_SHOCK_BP,
)

#: 书4 Ch9 bootstrap 例的零息曲线（连续复利），供曲线类用例共用
BOOTSTRAP_CURVE = {
    0.5: -np.log(0.991909) / 0.5,
    1.0: -np.log(0.980944) / 1.0,
    1.5: -np.log(0.969406) / 1.5,
    2.0: -np.log(0.956909) / 2.0,
}

FLAT_CURVE = {t: 0.03 for t in (0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0)}


class TestYtm:
    def test_par_bond_ytm_equals_coupon(self):
        """书4 Ch11：y = coupon 时平价（反解回验证）。"""
        sch = bonds.coupon_schedule(100.0, 0.04, 5.0)
        result = bonds.ytm(sch["times"], sch["amounts"], price=100.0)
        assert result["ytm"] == pytest.approx(0.04, abs=1e-8)
        assert result["method"] == "brentq"

    def test_known_price_yield_pair(self):
        """5 年 6% 半年付息债，y=5% → P = 3×年金 + 100×d，brentq 反解回 5%。"""
        sch = bonds.coupon_schedule(100.0, 0.06, 5.0)
        price = bonds.price_from_yield(sch["times"], sch["amounts"], 0.05)
        annuity = (1 - 1.025**-10) / 0.025
        assert price == pytest.approx(3.0 * annuity + 100.0 * 1.025**-10, abs=1e-10)
        assert price == pytest.approx(104.376, abs=1e-3)
        result = bonds.ytm(sch["times"], sch["amounts"], price)
        assert result["ytm"] == pytest.approx(0.05, abs=1e-10)

    def test_annuity_formula_eq11_3(self):
        """书4 Ch11 式 11.3：年金 V = (c/y)·[1 − (1+y/2)^{−2T}]（每期票息 c/2 口径）。"""
        sch = bonds.coupon_schedule(100.0, 0.05, 3.0)
        # 去掉本金的纯年金现金流
        price_annuity = bonds.price_from_yield(sch["times"], np.full(6, 2.5), 0.04)
        expected = (5.0 / 0.04) * (1 - 1.02**-6)
        assert price_annuity == pytest.approx(expected, abs=1e-10)

    def test_not_bracketed_rejected(self):
        sch = bonds.coupon_schedule(100.0, 0.01, 1.0)
        with pytest.raises(ValueError):
            bonds.ytm(sch["times"], sch["amounts"], price=500.0)


class TestAccruedAndClean:
    def test_actual_actual_eq9_2(self):
        """书4 Ch9 式 9.2：AI = c·(t/T)；半年票息 3，t=60，T=182 → 0.98901。"""
        result = bonds.accrued_interest(3.0, 60, 182)
        assert result["day_count"] == "actual/actual"
        assert result["accrued_interest"] == pytest.approx(3.0 * 60 / 182, abs=1e-12)

    def test_thirty_360_convention(self):
        """书3 Ch17 公司债 30/360：年票息 8，90 天 → 2.0。"""
        result = bonds.accrued_interest(8.0, 90, 180, day_count="30/360")
        assert result["accrued_interest"] == pytest.approx(2.0, abs=1e-12)

    def test_default_day_count_chinese_convention(self):
        assert DEFAULT_DAY_COUNT == "actual/actual"

    def test_dirty_clean_roundtrip(self):
        dirty = bonds.clean_to_dirty(101.25, 0.989011)["dirty_price"]
        assert dirty == pytest.approx(102.239011, abs=1e-12)
        assert bonds.dirty_to_clean(dirty, 0.989011)["clean_price"] == pytest.approx(101.25, abs=1e-12)

    def test_unknown_day_count_rejected(self):
        with pytest.raises(ValueError):
            bonds.accrued_interest(3.0, 60, 182, day_count="act/365")


class TestDurationConvexity:
    def test_flat_curve_annuity_analytic(self):
        """平坦曲线连续年金解析解核对（CR §4 R5 验收点）。

        连续票息流 1/年、连续复利 y=3%、T=10：
        P = (1−e^{−yT})/y = 8.6394；
        Macaulay D = (1/y)·(1−e^{−yT}(1+yT))/(1−e^{−yT}) = 4.7504；
        C = [2−e^{−yT}(y²T²+2yT+2)]/(y²(1−e^{−yT})) = 30.862。
        周付息网格（520 期）离散逼近，容差 rel 1e-2。
        """
        y, t_years = 0.03, 10.0
        n = int(t_years * 52)
        times = np.arange(1, n + 1) / 52
        cf = np.full(n, 1.0 / 52)
        result = bonds.yield_duration_convexity(times, cf, y, m=52)
        e = np.exp(-y * t_years)
        assert result["price"] == pytest.approx((1 - e) / y, rel=1e-2)
        assert result["macaulay_duration"] == pytest.approx(
            (1 / y) * (1 - e * (1 + y * t_years)) / (1 - e), rel=1e-2
        )
        assert result["yield_convexity"] == pytest.approx(
            (2 - e * (y * y * t_years**2 + 2 * y * t_years + 2)) / (y * y * (1 - e)), rel=1e-2
        )

    def test_modified_relations_eq12_6(self):
        """式 12.6：Modified D = Macaulay D/(1+y/m)；Modified C = C/(1+y/m)²。"""
        sch = bonds.coupon_schedule(100.0, 0.06, 5.0)
        result = bonds.yield_duration_convexity(sch["times"], sch["amounts"], 0.05, m=2)
        assert result["modified_duration"] == pytest.approx(
            result["macaulay_duration"] / 1.025, abs=1e-12
        )
        assert result["modified_convexity"] == pytest.approx(
            result["yield_convexity"] / 1.025**2, abs=1e-12
        )

    def test_zero_coupon_bond_macaulay_equals_maturity(self):
        """零息债 Macaulay D = 期限（权重全在到期现金流）。"""
        result = bonds.yield_duration_convexity([7.0], [100.0], 0.04, m=2)
        assert result["macaulay_duration"] == pytest.approx(7.0, abs=1e-12)
        assert result["yield_convexity"] == pytest.approx(49.0, abs=1e-12)

    def test_effective_matches_yield_on_option_free_bond(self):
        """无期权债：effective duration（曲线 ±1bp 重定价）≈ yield-based modified
        （同连续复利口径；数值差分二阶残差，rel 容差 1e-4）。"""
        sch = bonds.coupon_schedule(100.0, 0.03, 5.0)
        eff = bonds.effective_duration_convexity(sch["times"], sch["amounts"], FLAT_CURVE)
        # 连续复利 y=3% 下的 modified：m→∞ 时 D_mod = D_mac/(1+y/m) → D_mac
        yc = bonds.yield_duration_convexity(sch["times"], sch["amounts"], 0.03, m=10**6)
        assert eff["effective_duration"] == pytest.approx(yc["modified_duration"], rel=1e-4)
        assert eff["effective_convexity"] == pytest.approx(yc["modified_convexity"], rel=1e-3)


class TestDv01:
    def test_dv01_duration_conversion_identity(self):
        """D↔DV01 换算自洽（CR §4 验收点）：D = 10,000×DV01/Value，
        与同一 ±1bp 重定价的 effective duration 一致。"""
        sch = bonds.coupon_schedule(100.0, 0.03, 5.0)
        eff = bonds.effective_duration_convexity(sch["times"], sch["amounts"], FLAT_CURVE)
        d01 = bonds.dv01(sch["times"], sch["amounts"], FLAT_CURVE)
        d_from = bonds.duration_from_dv01(d01["dv01"], eff["price"])
        assert d_from["duration"] == pytest.approx(eff["effective_duration"], rel=1e-12)

    def test_dv01_from_duration_formula(self):
        """DV01 = Value×Modified D×1e-4：市值 100 万、D=12 → DV01=1200
        （书4 Ch12，同书3 Ch19 例 E_V = B·D·0.0001）。"""
        result = bonds.dv01_from_duration(1_000_000.0, 12.0)
        assert result["dv01"] == pytest.approx(1200.0, abs=1e-9)

    def test_hedge_face_ratio(self):
        """书3 Ch19 例：500 万、D=12 的组合，E_V=6000，E_F=165.2 → 空 36.3 份。"""
        port = bonds.dv01_from_duration(5_000_000.0, 12.0)["dv01"]
        result = bonds.dv01_hedge_face(port, 165.2)
        assert port == pytest.approx(6000.0, abs=1e-9)
        assert result["hedge_face"] == pytest.approx(-6000.0 / 165.2, abs=1e-9)
        assert result["hedge_face"] == pytest.approx(-36.319, abs=1e-3)


class TestPortfolio:
    def test_aggregation_rules(self):
        """书4 Ch12：DV01 可加；D/C 市值加权。"""
        positions = [
            {"name": "a", "market_value": 60.0, "duration": 4.0, "convexity": 20.0, "dv01": 240.0},
            {"name": "b", "market_value": 40.0, "duration": 7.0, "convexity": 50.0, "dv01": 280.0},
        ]
        result = bonds.portfolio_aggregate(positions)
        assert result["dv01"] == pytest.approx(520.0, abs=1e-12)
        assert result["duration"] == pytest.approx(0.6 * 4.0 + 0.4 * 7.0, abs=1e-12)
        assert result["convexity"] == pytest.approx(0.6 * 20.0 + 0.4 * 50.0, abs=1e-12)
        np.testing.assert_allclose(result["weights"], [0.6, 0.4], atol=1e-12)

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            bonds.portfolio_aggregate([])


class TestScenarioShocks:
    def test_parallel_shift_second_order(self):
        """式 12.4：ΔP = −D·P·Δr + ½CP(Δr)²；+100bp 时二阶近似与直接重定价
        偏差在合理容差内（rel < 1e-3，CR §4 验收点）。"""
        sch = bonds.coupon_schedule(100.0, 0.03, 5.0)
        eff = bonds.effective_duration_convexity(sch["times"], sch["amounts"], FLAT_CURVE)
        approx = bonds.parallel_shift_approx(
            eff["price"], eff["effective_duration"], eff["effective_convexity"], 0.01
        )
        direct = bonds.price_from_zero_curve(sch["times"], sch["amounts"], FLAT_CURVE, shift=0.01)
        assert approx["new_price"] == pytest.approx(direct, rel=1e-3)
        # 一阶（纯久期）项符号与幅度核对
        assert approx["delta_price"] < 0
        assert approx["delta_price"] == pytest.approx(
            -eff["effective_duration"] * eff["price"] * 0.01
            + 0.5 * eff["effective_convexity"] * eff["price"] * 0.01**2,
            abs=1e-12,
        )

    def test_kr01_sum_equals_dv01(self):
        """书4 Ch13 自检恒等式（CR §4 验收点）：ΣKR01 = DV01（一阶，rtol 1e-4）。"""
        sch = bonds.coupon_schedule(100.0, 0.03, 5.0)
        result = bonds.key_rate_shifts(
            sch["times"], sch["amounts"], FLAT_CURVE,
            key_tenors=(0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0),
        )
        assert result["kr01_sum_matches_dv01"] is True
        assert result["kr01_sum"] == pytest.approx(result["dv01"], rel=1e-4)
        # 5y 债的风险集中在 5y 节点
        tenors = list(result["key_tenors"])
        assert tenors[int(np.argmax(result["kr01"]))] == 5.0
        # 超过最长现金流的节点无暴露
        assert result["kr01"][tenors.index(7.0)] == pytest.approx(0.0, abs=1e-12)

    def test_key_rate_defaults_from_constants(self):
        assert RATE_SHOCK_BP == 1.0
        assert len(KEY_RATE_TENORS) >= 5

    def test_kr01_weights_sum_to_one(self):
        """权重自检：任意期限三角帽权重和 = 1（ΣKR01=DV01 的结构性来源）。"""
        sch = bonds.coupon_schedule(100.0, 0.03, 10.0)
        result = bonds.key_rate_shifts(sch["times"], sch["amounts"], FLAT_CURVE)
        assert result["kr01_sum_matches_dv01"] is True


class TestConvertibleBondFloor:
    def test_floor_discount_with_spread(self):
        """债底 = Σ CF·e^{−(r+s)·t}（手算核对，3 期现金流）。"""
        times = [0.5, 1.0, 1.5]
        cfs = [1.5, 1.5, 101.5]
        s = 0.02
        result = bonds.convertible_bond_floor(times, cfs, BOOTSTRAP_CURVE, credit_spread=s)
        expected = sum(
            cf * np.exp(-(BOOTSTRAP_CURVE[t] + s) * t) for t, cf in zip(times, cfs)
        )
        assert result["pure_bond_value"] == pytest.approx(expected, abs=1e-10)

    def test_zero_spread_equals_risk_free_price(self):
        sch = bonds.coupon_schedule(100.0, 0.03, 2.0)
        floor = bonds.convertible_bond_floor(
            sch["times"], sch["amounts"], BOOTSTRAP_CURVE, credit_spread=0.0
        )
        direct = bonds.price_from_zero_curve(sch["times"], sch["amounts"], BOOTSTRAP_CURVE)
        assert floor["pure_bond_value"] == pytest.approx(direct, abs=1e-12)

    def test_spread_duration_matches_effective_duration_flat(self):
        """书3 Ch17：spread duration ≈ 利差 +100bp 的价格百分比跌幅（平坦曲线下
        利差移动=平行移动 → spread duration = r+s 水平上的 effective duration）。"""
        sch = bonds.coupon_schedule(100.0, 0.03, 5.0)
        floor = bonds.convertible_bond_floor(
            sch["times"], sch["amounts"], FLAT_CURVE, credit_spread=0.02
        )
        curve_with_spread = {t: r + 0.02 for t, r in FLAT_CURVE.items()}
        eff = bonds.effective_duration_convexity(sch["times"], sch["amounts"], curve_with_spread)
        assert floor["spread_duration"] == pytest.approx(eff["effective_duration"], rel=1e-6)
        # 利差 +100bp 跌幅 ≈ spread duration×Δs − ½C(Δs)²（二阶口径核对）
        shocked = bonds.convertible_bond_floor(
            sch["times"], sch["amounts"], FLAT_CURVE, credit_spread=0.03
        )
        pct_drop = (floor["pure_bond_value"] - shocked["pure_bond_value"]) / floor["pure_bond_value"]
        expected = eff["effective_duration"] * 0.01 - 0.5 * eff["effective_convexity"] * 0.01**2
        assert pct_drop == pytest.approx(expected, rel=1e-3)
