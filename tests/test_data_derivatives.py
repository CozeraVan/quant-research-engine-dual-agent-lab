"""data.derivatives 单测：纯函数（收益率换算/期限映射/现金流/parity）真单测 + DB 冒烟（无库 skip）。

DB 依赖用例约定：仅当 QRE_MARKET_DB_URL（或 SR_MARKET_DB_URL）已设置且可连接时运行，
否则整组 skip——与仓库「单测不依赖真实库」的既有惯例一致（参照 tests/test_cli.py
对 DB URL 的隔离方式）。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from quant_research_engine.data import derivatives
from quant_research_engine.risk import rates


class TestYieldPercentToContinuous:
    def test_known_value(self):
        """2.35% → 0.0235 年复利 → 连续 Rc = ln(1.0235) ≈ 2.3228%。"""
        rc = derivatives.yield_percent_to_continuous(2.35)
        assert rc == pytest.approx(np.log1p(0.0235), abs=1e-15)

    def test_matches_rates_kernel(self):
        """口径 = rates.periodic_to_continuous(rate/100, m=1)。"""
        rc = derivatives.yield_percent_to_continuous(1.6839)
        expected = rates.periodic_to_continuous(0.016839, 1)["rate_out"]
        assert rc == pytest.approx(expected, abs=1e-15)

    def test_zero_yield(self):
        assert derivatives.yield_percent_to_continuous(0.0) == pytest.approx(0.0, abs=1e-15)


class TestCbCashflows:
    """cb_cashflows 纯函数：期限网格取整、票息与本金、异常分支。"""

    TERMS = {
        "ts_code": "110000.SH",
        "coupon_rate": 2.0,  # cb_basic 百分数口径
        "par": 100.0,
        "pay_per_year": 1,
        "maturity_date": date(2028, 6, 15),
    }

    def test_cashflow_grid_rounding(self):
        """剩余 913 天 ≈ 2.5 年按年付网格取整为 3 期；末期含本金。"""
        result = derivatives.cb_cashflows(self.TERMS, date(2025, 12, 15))
        assert result["grid_maturity"] == pytest.approx(3.0, abs=1e-9)
        times = list(result["times"])
        amounts = list(result["amounts"])
        assert times == [1.0, 2.0, 3.0]
        assert amounts[0] == pytest.approx(2.0)  # 100 × 2% / 1
        assert amounts[-1] == pytest.approx(102.0)

    def test_semiannual_frequency(self):
        """半年付：票息 = 面值 × 票息率 / 2，期限取整到 0.5 网格。"""
        terms = {**self.TERMS, "pay_per_year": 2}
        result = derivatives.cb_cashflows(terms, date(2025, 12, 16))
        assert result["grid_maturity"] == pytest.approx(2.5, abs=1e-9)
        assert list(result["amounts"])[:1] == [pytest.approx(1.0)]
        assert result["amounts"][-1] == pytest.approx(101.0)

    def test_defaults(self):
        """par/pay_per_year 缺失按 100 面值、年付；pay_per_year=0 异常值按年付。"""
        terms = {"ts_code": "X", "coupon_rate": 1.0, "pay_per_year": 0,
                 "maturity_date": date(2027, 1, 2)}
        result = derivatives.cb_cashflows(terms, date(2026, 1, 2))
        assert result["frequency"] == 1
        assert result["face"] == 100.0

    def test_expired_raises(self):
        with pytest.raises(ValueError, match="到期"):
            derivatives.cb_cashflows(self.TERMS, date(2029, 1, 1))

    def test_missing_maturity_date_raises(self):
        with pytest.raises(ValueError, match="maturity_date"):
            derivatives.cb_cashflows({"ts_code": "X"}, date(2026, 1, 1))


class TestEstimateSpotFromParity:
    def test_roundtrip(self):
        """S = (C − P) + K·e^{−rT}：构造已知 S 反推可还原。"""
        S, K, r, T = 2.9934, 2.75, 0.0117, 5 / 365
        synthetic_gap = S - K * np.exp(-r * T)  # C − P
        est = derivatives.estimate_spot_from_parity(synthetic_gap + 0.2, 0.2, K, r, T)
        assert est == pytest.approx(S, abs=1e-9)

    def test_invalid_T(self):
        with pytest.raises(ValueError, match="T must be > 0"):
            derivatives.estimate_spot_from_parity(0.1, 0.1, 2.75, 0.02, 0.0)


class TestAsDate:
    def test_formats(self):
        assert derivatives._as_date("2026-08-21") == date(2026, 8, 21)
        assert derivatives._as_date("20260821") == date(2026, 8, 21)
        assert derivatives._as_date(date(2026, 8, 21)) == date(2026, 8, 21)


# ---------------------------------------------------------------------------
# DB 依赖用例（真实库冒烟；无 QRE_MARKET_DB_URL 或不可连接时整组 skip）
# ---------------------------------------------------------------------------


def _db_available() -> bool:
    import os

    if not (os.environ.get("QRE_MARKET_DB_URL") or os.environ.get("SR_MARKET_DB_URL")):
        return False
    try:
        engine = derivatives._default_engine()
        with engine.begin() as conn:
            from sqlalchemy import text

            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="QRE_MARKET_DB_URL 未设置或库不可连接")


@requires_db
class TestDerivativesDbSmoke:
    def test_zero_curve_pillars(self):
        """曲线 ≥8 节点（CR D2 验收修订值），利率在 0–10% 合理区间。"""
        curve = derivatives.load_zero_curve("2026-08-21")
        assert len(curve) >= 8
        assert all(0.0 <= r <= 0.10 for r in curve.values())
        assert derivatives.latest_curve_date("2026-08-21") == date(2026, 8, 21)

    def test_zero_curve_fallback_date(self):
        """非交易日（周日）取最近有数据日，且与显式请求该日结果一致。"""
        fallback = derivatives.latest_curve_date("2026-08-23")
        assert fallback is not None and fallback <= date(2026, 8, 23)
        assert derivatives.load_zero_curve("2026-08-23") == derivatives.load_zero_curve(fallback)

    def test_cb_terms_and_floor(self):
        """存续转债条款可读、债底为正且 spread_duration 在 0–10（CR D1 验收）。"""
        floor = derivatives.cb_bond_floor("113052.SH", "2026-08-21")
        assert floor["pure_bond_value"] > 0
        assert 0.0 <= floor["spread_duration"] <= 10.0
        assert floor["cb_daily_bond_value"] is not None  # bond_value 交叉验证数据在场

    def test_option_chain_atm_iv(self):
        """50ETF 平值 call/put 隐波落在 (1%, 150%)（loader 内断言 + 显式复核）。"""
        chain = derivatives.load_option_chain("2026-08-21", underlying_price=2.9934)
        assert 0.01 <= chain["atm"]["call_iv"] <= 1.5
        assert 0.01 <= chain["atm"]["put_iv"] <= 1.5
        assert chain["risk_free_rate"] > 0
        assert len(chain["chain"]) > 0
