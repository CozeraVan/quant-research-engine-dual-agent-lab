"""利率内核：复利换算、折现因子、零息曲线 bootstrap、远期利率。

- 复利换算（书3 Ch16 式 16.1–16.5）：FV = A(1+R/m)^{mT}；连续复利 FV = A·e^{RT}；
  频率换算 R2 = m2·[(1+R1/m1)^{m1/m2} − 1]；Rc = m·ln(1+Rm/m)、Rm = m(e^{Rc/m}−1)。
- Spot↔折现因子（书4 Ch10）：半年复利 d(t)=(1+r(t)/2)^{−2t}；连续 d(t)=e^{−r(t)t}。
- Bootstrap（书4 Ch9）：附息债由短到长逐个解折现因子
  Σ coupon×d(已知) + 到期现金流×d(k) = dirty price。
- 插值：linear（零息利率线性）/ log_linear（折现因子对数线性，远期分段常数），
  集中参数 CURVE_INTERPOLATION；域外平坦外推（披露）。
- 远期利率：连续 F=(R2T2−R1T1)/(T2−T1)；半年复利式 10.5 先求增长因子比。
- Par yield（书3 Ch16 式 16.7 / 书4 Ch10 式 10.4）：c = (100 − 100·d)·m/A。

曲线统一约定：零息利率为**连续复利**年化（小数），期限单位为年。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from quant_research_engine.risk.constants import CURVE_INTERPOLATION

_INTERPOLATIONS = ("linear", "log_linear")


def convert_compounding(rate: float, m_from: int, m_to: int) -> dict[str, Any]:
    """复利频率换算 R2 = m2·[(1+R1/m1)^{m1/m2} − 1]（书3 Ch16 式 16.2）。"""
    if m_from < 1 or m_to < 1:
        raise ValueError("compounding frequency must be >= 1")
    converted = m_to * ((1.0 + rate / m_from) ** (m_from / m_to) - 1.0)
    return {
        "rate_in": rate,
        "m_from": m_from,
        "m_to": m_to,
        "rate_out": float(converted),
        "note": "R2 = m2·[(1+R1/m1)^{m1/m2} − 1]（书3 Ch16 式 16.2）",
    }


def periodic_to_continuous(rate: float, m: int) -> dict[str, Any]:
    """复利利率 → 连续复利 Rc = m·ln(1+Rm/m)（书3 Ch16 式 16.4）。"""
    if m < 1:
        raise ValueError("compounding frequency must be >= 1")
    rc = m * np.log1p(rate / m)
    return {
        "rate_in": rate,
        "m": m,
        "rate_out": float(rc),
        "note": "Rc = m·ln(1+Rm/m)（书3 Ch16 式 16.4）",
    }


def continuous_to_periodic(rate: float, m: int) -> dict[str, Any]:
    """连续复利 → m 次复利 Rm = m·(e^{Rc/m} − 1)（书3 Ch16 式 16.5）。"""
    if m < 1:
        raise ValueError("compounding frequency must be >= 1")
    rm = m * (np.exp(rate / m) - 1.0)
    return {
        "rate_in": rate,
        "m": m,
        "rate_out": float(rm),
        "note": "Rm = m·(e^{Rc/m} − 1)（书3 Ch16 式 16.5）",
    }


def future_value(amount: float, rate: float, t: float, m: int | None = None) -> dict[str, Any]:
    """终值：m=None → 连续复利 A·e^{RT}（式 16.3）；否则 A(1+R/m)^{mT}（式 16.1）。"""
    if t < 0:
        raise ValueError("t must be >= 0")
    fv = amount * (np.exp(rate * t) if m is None else (1.0 + rate / m) ** (m * t))
    return {
        "amount": amount,
        "rate": rate,
        "t": t,
        "m": m,
        "compounding": "continuous" if m is None else "periodic",
        "future_value": float(fv),
        "note": "FV = A·e^{RT}（连续，式 16.3）或 A(1+R/m)^{mT}（式 16.1）",
    }


def present_value(amount: float, rate: float, t: float, m: int | None = None) -> dict[str, Any]:
    """现值：连续 A·e^{−RT}；否则 A(1+R/m)^{−mT}（书3 Ch16）。"""
    if t < 0:
        raise ValueError("t must be >= 0")
    pv = amount * (np.exp(-rate * t) if m is None else (1.0 + rate / m) ** (-m * t))
    return {
        "amount": amount,
        "rate": rate,
        "t": t,
        "m": m,
        "compounding": "continuous" if m is None else "periodic",
        "present_value": float(pv),
        "note": "PV = A·e^{−RT}（连续）或 A(1+R/m)^{−mT}（书3 Ch16）",
    }


def spot_to_discount_factor(rate: float, t: float, m: int | None = None) -> dict[str, Any]:
    """Spot → 折现因子：连续 d=e^{−rt}；半年复利等 d=(1+r/m)^{−mt}（书4 Ch10）。"""
    if t <= 0:
        raise ValueError("t must be > 0")
    d = np.exp(-rate * t) if m is None else (1.0 + rate / m) ** (-m * t)
    return {
        "rate": rate,
        "t": t,
        "m": m,
        "compounding": "continuous" if m is None else "periodic",
        "discount_factor": float(d),
        "note": "d(t) = e^{−r(t)t}（连续）或 (1+r/m)^{−mt}（书4 Ch10）",
    }


def discount_factor_to_spot(d: float, t: float, m: int | None = None) -> dict[str, Any]:
    """折现因子 → spot：连续 r = −ln d / t；否则 r = m·(d^{−1/(mt)} − 1)。"""
    if t <= 0:
        raise ValueError("t must be > 0")
    if not 0.0 < d <= 1.0:
        raise ValueError("discount factor must be in (0, 1]")
    r = -np.log(d) / t if m is None else m * (d ** (-1.0 / (m * t)) - 1.0)
    return {
        "discount_factor": d,
        "t": t,
        "m": m,
        "compounding": "continuous" if m is None else "periodic",
        "rate": float(r),
        "note": "r = −ln d / t（连续）或 m·(d^{−1/(mt)} − 1)（书4 Ch10 逆运算）",
    }


def _check_curve(times: np.ndarray, rates: np.ndarray) -> None:
    if times.ndim != 1 or len(times) < 2:
        raise ValueError("curve needs at least 2 pillar times")
    if np.any(times <= 0):
        raise ValueError("curve times must be > 0")
    if np.any(np.diff(times) <= 0):
        raise ValueError("curve times must be strictly increasing")
    if len(times) != len(rates):
        raise ValueError("curve times and rates must have equal length")


def interp_zero_rate(
    curve: dict[float, float] | tuple[np.ndarray, np.ndarray],
    t: float | np.ndarray,
    interpolation: str = CURVE_INTERPOLATION,
) -> np.ndarray:
    """在零息曲线（连续复利，{期限: 利率} 或 (times, rates)）上插值出 r(t)。

    - linear：零息利率线性插值。
    - log_linear：折现因子对数线性插值（等价远期利率分段常数）。
    域外平坦外推（端点值），披露于调用方结果 dict。
    """
    if interpolation not in _INTERPOLATIONS:
        raise ValueError(f"interpolation must be one of {_INTERPOLATIONS}")
    if isinstance(curve, dict):
        times = np.array(sorted(curve), dtype=float)
        rates = np.array([curve[k] for k in sorted(curve)], dtype=float)
    else:
        times = np.asarray(curve[0], dtype=float)
        rates = np.asarray(curve[1], dtype=float)
    _check_curve(times, rates)
    t_arr = np.asarray(t, dtype=float)
    if interpolation == "linear":
        return np.interp(t_arr, times, rates)
    log_df = -rates * times
    return -np.interp(t_arr, times, log_df) / t_arr


def bootstrap_zero_curve(
    bonds: list[dict[str, float]],
    frequency: int = 2,
) -> dict[str, Any]:
    """附息债 bootstrap 零息曲线（书4 Ch9）。

    输入 bonds：每项 {"maturity": 年, "coupon_rate": 年票息率（小数，面值 100）,
    "price": dirty price（面值 100）}；要求期限按付息频率等距网格
    （每期一个节点，早期付息日与已解出节点重合）。按期限由短到长递推：
    d(k) = (price − Σ coupon·d(已知节点)) / (100 + coupon)。
    输出连续复利零息利率 r(t) = −ln d(t)/t。
    """
    if frequency < 1:
        raise ValueError("frequency must be >= 1")
    if not bonds:
        raise ValueError("bonds must be non-empty")
    ordered = sorted(bonds, key=lambda b: b["maturity"])
    step = 1.0 / frequency
    known: dict[float, float] = {}
    for bond in ordered:
        maturity = float(bond["maturity"])
        coupon = 100.0 * float(bond["coupon_rate"]) / frequency
        price = float(bond["price"])
        n_periods = round(maturity * frequency)
        if abs(n_periods - maturity * frequency) > 1e-9 or n_periods < 1:
            raise ValueError(f"maturity {maturity} not on {frequency}x payment grid")
        pay_times = [round(i * step, 9) for i in range(1, n_periods + 1)]
        known_pv = 0.0
        for pt in pay_times[:-1]:
            if pt not in known:
                raise ValueError(f"payment time {pt} has no bootstrapped discount factor yet")
            known_pv += coupon * known[pt]
        final_cf = 100.0 + coupon
        d = (price - known_pv) / final_cf
        if not 0.0 < d <= 1.0:
            raise ValueError(f"bootstrapped discount factor {d} at t={maturity} out of (0, 1]")
        known[pay_times[-1]] = d
    times = np.array(sorted(known), dtype=float)
    dfs = np.array([known[k] for k in sorted(known)], dtype=float)
    zero_rates = -np.log(dfs) / times
    return {
        "method": "bootstrap_coupon_bonds",
        "frequency": frequency,
        "times": times,
        "discount_factors": dfs,
        "zero_rates": zero_rates,
        "compounding": "continuous",
        "n_bonds": len(ordered),
        "note": "书4 Ch9：d(k) = (dirty price − Σ coupon·d(已知)) / 到期现金流；零息利率连续复利",
    }


def forward_rate(
    r1: float,
    t1: float,
    r2: float,
    t2: float,
    m: int | None = None,
) -> dict[str, Any]:
    """远期利率（t1→t2）。

    - 连续复利（m=None）：F = (R2·T2 − R1·T1)/(T2 − T1)（书3 Ch16）。
    - m 次复利（书4 Ch10 式 10.5 半年复利推广）：由增长因子比
      (1+F/m)^{m(t2−t1)} = (1+R2/m)^{m·t2} / (1+R1/m)^{m·t1} 解出 F。
    """
    if not 0.0 < t1 < t2:
        raise ValueError("need 0 < t1 < t2")
    if m is None:
        fwd = (r2 * t2 - r1 * t1) / (t2 - t1)
        formula = "F = (R2T2 − R1T1)/(T2 − T1)（连续复利，书3 Ch16）"
    else:
        growth = (1.0 + r2 / m) ** (m * t2) / (1.0 + r1 / m) ** (m * t1)
        fwd = m * (growth ** (1.0 / (m * (t2 - t1))) - 1.0)
        formula = "增长因子比解 (1+F/m)^{m(t2−t1)} = V2/V1（书4 Ch10 式 10.5）"
    return {
        "r1": r1,
        "t1": t1,
        "r2": r2,
        "t2": t2,
        "m": m,
        "compounding": "continuous" if m is None else "periodic",
        "forward_rate": float(fwd),
        "note": formula,
    }


def par_yield(discount_factors: list[float] | np.ndarray, frequency: int = 2) -> dict[str, Any]:
    """Par yield：c = (100 − 100·d(T))·m / A（书3 Ch16 式 16.7 / 书4 Ch10 式 10.4）。

    discount_factors = 各付息日折现因子（含到期日），A = Σ d(t_i) 为年金因子，
    最后一个为到期折现因子 d(T)。返回年化票息率（小数，面值 100 口径）。
    """
    dfs = np.asarray(discount_factors, dtype=float)
    if dfs.ndim != 1 or len(dfs) < 1:
        raise ValueError("discount_factors must be a non-empty 1-D array")
    annuity = float(dfs.sum())
    c = (1.0 - float(dfs[-1])) * frequency / annuity
    return {
        "frequency": frequency,
        "n_payments": int(len(dfs)),
        "annuity_factor": annuity,
        "terminal_discount_factor": float(dfs[-1]),
        "par_yield": float(c),
        "note": "c = (100 − 100·d(T))·m/A（式 16.7/10.4，使价格=面值的票息率）",
    }
