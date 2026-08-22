"""risk.rates 单测：教材例题解析值 + 手算核对 + 自检恒等式。"""

from __future__ import annotations

import numpy as np
import pytest

from quant_research_engine.risk import rates
from quant_research_engine.risk.constants import CURVE_INTERPOLATION


class TestCompoundingConversions:
    def test_frequency_conversion_eq16_2(self):
        """书3 Ch16 式 16.2：10% 半年复利 → 年复利 m2[(1+0.1/2)^{2/1}−1] = 10.25%。"""
        result = rates.convert_compounding(0.10, m_from=2, m_to=1)
        assert result["rate_out"] == pytest.approx(0.1025, abs=1e-12)

    def test_periodic_continuous_roundtrip(self):
        """式 16.4/16.5 互逆：Rc = m·ln(1+Rm/m)，Rm = m(e^{Rc/m}−1)。"""
        rc = rates.periodic_to_continuous(0.08, m=4)["rate_out"]
        assert rc == pytest.approx(4 * np.log1p(0.02), abs=1e-15)
        back = rates.continuous_to_periodic(rc, m=4)["rate_out"]
        assert back == pytest.approx(0.08, abs=1e-12)

    def test_continuous_to_periodic_known_value(self):
        """8% 连续复利 → 年复利 = e^{0.08}−1 = 8.3287%（教材惯例例值）。"""
        result = rates.continuous_to_periodic(0.08, m=1)
        assert result["rate_out"] == pytest.approx(0.083287, abs=1e-6)

    def test_invalid_frequency(self):
        with pytest.raises(ValueError):
            rates.convert_compounding(0.05, 0, 2)


class TestPvFv:
    def test_future_value_continuous_eq16_3(self):
        """式 16.3：100·e^{0.05×3} = 116.1834。"""
        result = rates.future_value(100.0, 0.05, 3.0)
        assert result["compounding"] == "continuous"
        assert result["future_value"] == pytest.approx(116.1834, abs=1e-4)

    def test_future_value_periodic_eq16_1(self):
        """式 16.1：100(1+0.06/2)^{2×2} = 112.5509。"""
        result = rates.future_value(100.0, 0.06, 2.0, m=2)
        assert result["future_value"] == pytest.approx(112.5509, abs=1e-4)

    def test_pv_fv_inverse(self):
        fv = rates.future_value(100.0, 0.04, 5.0, m=2)["future_value"]
        pv = rates.present_value(fv, 0.04, 5.0, m=2)["present_value"]
        assert pv == pytest.approx(100.0, abs=1e-10)

    def test_negative_time_rejected(self):
        with pytest.raises(ValueError):
            rates.future_value(100.0, 0.05, -1.0)


class TestSpotDiscountFactor:
    def test_semiannual_d(self):
        """书4 Ch10：半年复利 d(t) = (1+r/2)^{−2t}；r=5%, t=1.5 → 0.928597。"""
        result = rates.spot_to_discount_factor(0.05, 1.5, m=2)
        assert result["discount_factor"] == pytest.approx((1.025) ** -3, abs=1e-12)
        assert result["discount_factor"] == pytest.approx(0.928599, abs=1e-6)

    def test_continuous_roundtrip(self):
        d = rates.spot_to_discount_factor(0.03, 7.0)["discount_factor"]
        r = rates.discount_factor_to_spot(d, 7.0)["rate"]
        assert r == pytest.approx(0.03, abs=1e-12)

    def test_periodic_roundtrip(self):
        d = rates.spot_to_discount_factor(0.045, 3.0, m=2)["discount_factor"]
        r = rates.discount_factor_to_spot(d, 3.0, m=2)["rate"]
        assert r == pytest.approx(0.045, abs=1e-12)

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            rates.discount_factor_to_spot(1.5, 1.0)
        with pytest.raises(ValueError):
            rates.spot_to_discount_factor(0.03, 0.0)


class TestBootstrap:
    """书4 Ch9 附息债 bootstrap 折现因子例。

    四只半年付息债（面值 100，dirty price）：
    maturities 0.5/1/1.5/2 年、coupons 5.75%/5.5%/5.875%/5.5%、
    prices 102.042638/103.519746/105.583486/106.413612
    → d = 0.991909/0.980944/0.969406/0.956909（教材示例值）。
    """

    BONDS = [
        {"maturity": 0.5, "coupon_rate": 0.0575, "price": 102.042638375},
        {"maturity": 1.0, "coupon_rate": 0.055, "price": 103.51974575},
        {"maturity": 1.5, "coupon_rate": 0.05875, "price": 105.5834858125},
        {"maturity": 2.0, "coupon_rate": 0.055, "price": 106.413612},
    ]
    TARGET_D = [0.991909, 0.980944, 0.969406, 0.956909]

    def test_textbook_discount_factors(self):
        result = rates.bootstrap_zero_curve(self.BONDS)
        np.testing.assert_allclose(result["discount_factors"], self.TARGET_D, atol=1e-6)
        np.testing.assert_allclose(result["times"], [0.5, 1.0, 1.5, 2.0], atol=1e-12)

    def test_repricing_self_consistency(self):
        """bootstrap 出的曲线折现回各债券现金流 = 输入 dirty price。"""
        result = rates.bootstrap_zero_curve(self.BONDS)
        dfs = result["discount_factors"]
        for bond, d_T in zip(self.BONDS, self.TARGET_D):
            n = int(round(bond["maturity"] * 2))
            coupon = 100.0 * bond["coupon_rate"] / 2
            pv = sum(coupon * dfs[i] for i in range(n - 1)) + (100.0 + coupon) * d_T
            assert pv == pytest.approx(bond["price"], abs=1e-6)

    def test_zero_rates_continuous(self):
        """r(t) = −ln d(t)/t：d(2)=0.956909 → r(2) ≈ 2.2024%（连续复利）。"""
        result = rates.bootstrap_zero_curve(self.BONDS)
        assert result["compounding"] == "continuous"
        assert result["zero_rates"][-1] == pytest.approx(-np.log(0.956909) / 2.0, abs=1e-12)
        assert result["zero_rates"][-1] == pytest.approx(0.022024, abs=1e-6)

    def test_par_yield_textbook(self):
        """式 16.7/10.4：c = (100−100·d)·m/A，A=Σd=3.899168 → c ≈ 2.2103%。"""
        result = rates.par_yield(self.TARGET_D, frequency=2)
        annuity = sum(self.TARGET_D)
        expected = (1.0 - self.TARGET_D[-1]) * 2 / annuity
        assert result["annuity_factor"] == pytest.approx(annuity, abs=1e-12)
        assert result["par_yield"] == pytest.approx(expected, abs=1e-12)
        assert result["par_yield"] == pytest.approx(0.022103, abs=1e-6)

    def test_par_yield_prices_at_par(self):
        """票息 = par yield 的债券按该曲线折现恰为面值 100（自检）。"""
        c = rates.par_yield(self.TARGET_D, frequency=2)["par_yield"]
        pv = sum(100.0 * c / 2 * d for d in self.TARGET_D[:-1]) + (100.0 + 100.0 * c / 2) * self.TARGET_D[-1]
        assert pv == pytest.approx(100.0, abs=1e-8)

    def test_off_grid_maturity_rejected(self):
        with pytest.raises(ValueError):
            rates.bootstrap_zero_curve([{"maturity": 0.7, "coupon_rate": 0.05, "price": 100.0}])


class TestInterpolation:
    CURVE = {0.5: 0.016249, 1.0: 0.019240, 1.5: 0.020703, 2.0: 0.022024}

    def test_linear_on_rates(self):
        r = rates.interp_zero_rate(self.CURVE, 0.75, interpolation="linear")
        assert r == pytest.approx((0.016249 + 0.019240) / 2, abs=1e-12)

    def test_log_linear_on_discount_factors(self):
        """对数线性 = 折现因子对数线性：节点间远期利率分段常数。"""
        r = rates.interp_zero_rate(self.CURVE, 0.75, interpolation="log_linear")
        log_df_expected = -0.5 * (0.5 * 0.016249 + 1.0 * 0.019240)
        assert r == pytest.approx(-log_df_expected / 0.75, abs=1e-12)

    def test_default_from_constants(self):
        assert CURVE_INTERPOLATION == "linear"

    def test_flat_extrapolation(self):
        """域外平坦外推（披露口径）。"""
        assert rates.interp_zero_rate(self.CURVE, 0.1) == pytest.approx(0.016249)
        assert rates.interp_zero_rate(self.CURVE, 5.0) == pytest.approx(0.022024)

    def test_unknown_method_rejected(self):
        with pytest.raises(ValueError):
            rates.interp_zero_rate(self.CURVE, 0.75, interpolation="cubic")


class TestForwardRate:
    def test_continuous_formula(self):
        """F = (R2T2 − R1T1)/(T2 − T1)：R1=1.92%(1y), R2=2.202%(2y) → 2.484%。"""
        result = rates.forward_rate(0.019240, 1.0, 0.022024, 2.0)
        assert result["forward_rate"] == pytest.approx(2 * 0.022024 - 0.019240, abs=1e-12)
        assert result["forward_rate"] == pytest.approx(0.024808, abs=1e-6)

    def test_semiannual_eq10_5(self):
        """式 10.5 半年复利：增长因子比解 F；(1+F/2)^{2(t2−t1)} = V2/V1。"""
        result = rates.forward_rate(0.02, 1.0, 0.025, 2.0, m=2)
        growth = (1.0125) ** 4 / (1.01) ** 2
        expected = 2 * (growth ** (1 / 2.0) - 1)
        assert result["forward_rate"] == pytest.approx(expected, abs=1e-12)

    def test_flat_curve_forward_equals_spot(self):
        """平坦曲线任意区间远期 = 即期（连续复利口径）。"""
        result = rates.forward_rate(0.03, 1.0, 0.03, 5.0)
        assert result["forward_rate"] == pytest.approx(0.03, abs=1e-12)

    def test_invalid_tenor_order(self):
        with pytest.raises(ValueError):
            rates.forward_rate(0.02, 2.0, 0.03, 1.0)
