"""债券内核：YTM、dirty/clean、久期/凸性/DV01、组合聚合、利率情景冲击、转债债底。

- YTM（书4 Ch11 式 11.1/11.2）：单一折现率使 Σ CF·(1+y/m)^{−m·t} = 价格，
  scipy.optimize.brentq 反解，区间集中参数 YTM_BRACKET。
- 应计利息（书4 Ch9 式 9.2 actual/actual；书3 Ch17 30/360 公司债惯例）：
  day count 参数化，默认 actual/actual（中国债券惯例，CR §4 约束）。
- 久期/凸性（书4 Ch12 式 12.6）：Macaulay D = (1/P)Σ t_i·c_i·e^{−y·t_i}；
  Modified D = Macaulay D/(1+y/m)；Yield C = (1/P)Σ t_i²·c_i·e^{−y·t_i}；
  Modified C = C/(1+y/m)²。
- Effective duration/convexity（式 12.1/12.3）：曲线 ±Δr 平移重定价，
  供含权债（转债）使用；Δr 集中参数 RATE_SHOCK_BP。
- DV01（式 12.1 注）：DV01 = Modified D × 市值 × 1bp；D = 10,000×DV01/Value。
- 组合（书4 Ch12）：DV01 可加；duration/convexity 市值加权；
  对冲面值 = 组合DV01/工具每面值DV01。
- 情景冲击：平行移动二阶近似 ΔP = −D·P·Δr + ½CP(Δr)²（式 12.4）；
  key-rate 扭转 KR01（书4 Ch13，端点外延的三角帽局部线性 shift，
  权重恒有 Σ=1 → ΣKR01=DV01 自检）。
- 转债债底（书3 Ch16/17 落地提示）：现金流按无风险零息曲线折现再乘
  信用因子 e^{−s·t}（s=信用利差，连续）；spread duration = 利差 ±Δs 重定价。

曲线约定与 rates.py 一致：连续复利零息利率（小数），期限单位为年。
现金流输入为 (times, amounts)：times 为年（距估值日），amounts 为金额。
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import optimize

from quant_research_engine.risk.constants import (
    CURVE_INTERPOLATION,
    DEFAULT_DAY_COUNT,
    KEY_RATE_TENORS,
    RATE_SHOCK_BP,
    YTM_BRACKET,
)
from quant_research_engine.risk.rates import interp_zero_rate

DAY_COUNT_CONVENTIONS = ("actual/actual", "30/360")


def coupon_schedule(
    face: float,
    coupon_rate: float,
    maturity: float,
    frequency: int = 2,
) -> dict[str, Any]:
    """附息债现金流表（估值日恰为付息日口径）：times（年）与 amounts。

    每期票息 = face × coupon_rate / frequency，到期加还本金。
    """
    if frequency < 1:
        raise ValueError("frequency must be >= 1")
    n_periods = round(maturity * frequency)
    if abs(n_periods - maturity * frequency) > 1e-9 or n_periods < 1:
        raise ValueError(f"maturity {maturity} not on {frequency}x payment grid")
    step = 1.0 / frequency
    coupon = face * coupon_rate / frequency
    times = np.array([i * step for i in range(1, n_periods + 1)], dtype=float)
    amounts = np.full(n_periods, coupon, dtype=float)
    amounts[-1] += face
    return {
        "face": face,
        "coupon_rate": coupon_rate,
        "maturity": maturity,
        "frequency": frequency,
        "times": times,
        "amounts": amounts,
        "note": "估值日=付息日（无应计）；每期票息 = face×coupon_rate/frequency，到期加本金",
    }


def price_from_yield(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    ytm: float,
    m: int = 2,
) -> float:
    """按单一收益率折现 P = Σ CF_i·(1+y/m)^{−m·t_i}（书4 Ch11 式 11.2）。"""
    t = np.asarray(times, dtype=float)
    cf = np.asarray(amounts, dtype=float)
    return float(np.sum(cf * (1.0 + ytm / m) ** (-m * t)))


def ytm(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    price: float,
    m: int = 2,
    bracket: tuple[float, float] = YTM_BRACKET,
) -> dict[str, Any]:
    """YTM 反解（scipy.optimize.brentq；书4 Ch11 迭代求解）。"""
    if price <= 0:
        raise ValueError("price must be > 0")
    lo, hi = bracket
    f_lo = price_from_yield(times, amounts, lo, m) - price
    f_hi = price_from_yield(times, amounts, hi, m) - price
    if f_lo * f_hi > 0:
        raise ValueError(f"YTM not bracketed in {bracket}: f(lo)={f_lo:.6g}, f(hi)={f_hi:.6g}")
    y = float(optimize.brentq(lambda r: price_from_yield(times, amounts, r, m) - price, lo, hi))
    return {
        "method": "brentq",
        "bracket": bracket,
        "m": m,
        "price": price,
        "ytm": y,
        "note": "P = Σ CF·(1+y/m)^{−m·t}（书4 Ch11 式 11.1/11.2），brentq 反解",
    }


def accrued_interest(
    coupon_amount: float,
    days_since_last_coupon: int,
    days_in_period: int,
    day_count: str = DEFAULT_DAY_COUNT,
) -> dict[str, Any]:
    """应计利息：actual/actual → c·(t/T)（书4 Ch9 式 9.2）；30/360 → coupon×days/360
    （书3 Ch17 公司债惯例，coupon_amount 传年票息额）。"""
    if day_count not in DAY_COUNT_CONVENTIONS:
        raise ValueError(f"day_count must be one of {DAY_COUNT_CONVENTIONS}")
    if days_since_last_coupon < 0:
        raise ValueError("days_since_last_coupon must be >= 0")
    if day_count == "actual/actual":
        if days_in_period <= 0:
            raise ValueError("days_in_period must be > 0")
        ai = coupon_amount * days_since_last_coupon / days_in_period
    else:
        ai = coupon_amount * days_since_last_coupon / 360.0
    return {
        "coupon_amount": coupon_amount,
        "days_since_last_coupon": days_since_last_coupon,
        "days_in_period": days_in_period,
        "day_count": day_count,
        "accrued_interest": float(ai),
        "note": "actual/actual: AI = c·(t/T)（式 9.2）；30/360: AI = coupon×days/360（书3 Ch17）",
    }


def clean_to_dirty(clean_price: float, accrued: float) -> dict[str, Any]:
    """Dirty = Clean + AI（书4 Ch9）。"""
    return {
        "clean_price": clean_price,
        "accrued_interest": accrued,
        "dirty_price": clean_price + accrued,
        "note": "Dirty = Clean + AI（书4 Ch9；中国国债 clean 报价须先转 dirty 再折现）",
    }


def dirty_to_clean(dirty_price: float, accrued: float) -> dict[str, Any]:
    """Clean = Dirty − AI（书4 Ch9）。"""
    return {
        "dirty_price": dirty_price,
        "accrued_interest": accrued,
        "clean_price": dirty_price - accrued,
        "note": "Clean = Dirty − AI（书4 Ch9）",
    }


def yield_duration_convexity(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    y: float,
    m: int = 2,
) -> dict[str, Any]:
    """Macaulay/Modified duration 与 yield convexity（书4 Ch12 式 12.6）。

    PV 按 m 次复利 (1+y/m)^{−m·t} 计算；Macaulay D（年）与 yield convexity
    按教材连续复利权重定义（D = (1/P)Σ t·PV_i，C = (1/P)Σ t²·PV_i），
    Modified D = D/(1+y/m)、Modified C = C/(1+y/m)²。
    """
    t = np.asarray(times, dtype=float)
    cf = np.asarray(amounts, dtype=float)
    pv = cf * (1.0 + y / m) ** (-m * t)
    price = float(pv.sum())
    if price <= 0:
        raise ValueError("bond present value must be > 0")
    macaulay = float(np.sum(t * pv) / price)
    convexity = float(np.sum(t * t * pv) / price)
    factor = 1.0 + y / m
    return {
        "ytm": y,
        "m": m,
        "price": price,
        "macaulay_duration": macaulay,
        "modified_duration": macaulay / factor,
        "yield_convexity": convexity,
        "modified_convexity": convexity / factor**2,
        "note": "书4 Ch12 式 12.6：Macaulay D=(1/P)Σ t·PV_i，Modified D=D/(1+y/m)；"
        "Yield C=(1/P)Σ t²·PV_i，Modified C=C/(1+y/m)²",
    }


def price_from_zero_curve(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    curve: dict[float, float] | tuple[np.ndarray, np.ndarray],
    shift: float = 0.0,
    interpolation: str = CURVE_INTERPOLATION,
) -> float:
    """按零息曲线（连续复利）折现：P = Σ CF_i·e^{−(r(t_i)+shift)·t_i}。

    shift 为平行移动（小数），供情景冲击与 ±Δr 重定价使用。
    """
    t = np.asarray(times, dtype=float)
    cf = np.asarray(amounts, dtype=float)
    rates = interp_zero_rate(curve, t, interpolation)
    return float(np.sum(cf * np.exp(-(rates + shift) * t)))


def effective_duration_convexity(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    curve: dict[float, float] | tuple[np.ndarray, np.ndarray],
    shock_bp: float = RATE_SHOCK_BP,
    interpolation: str = CURVE_INTERPOLATION,
) -> dict[str, Any]:
    """Effective duration/convexity（书4 Ch12 式 12.1/12.3）：曲线 ±Δr 平移重定价。

    D = (P− − P+)/(2·P·Δr)；C = (P+ + P− − 2P)/(P·(Δr)²)。
    供含权债（转债）与无解析久期工具使用。
    """
    dr = shock_bp * 1e-4
    p_mid = price_from_zero_curve(times, amounts, curve, 0.0, interpolation)
    p_down = price_from_zero_curve(times, amounts, curve, +dr, interpolation)
    p_up = price_from_zero_curve(times, amounts, curve, -dr, interpolation)
    if p_mid <= 0:
        raise ValueError("bond present value must be > 0")
    duration = (p_up - p_down) / (2.0 * p_mid * dr)
    convexity = (p_down + p_up - 2.0 * p_mid) / (p_mid * dr * dr)
    return {
        "shock_bp": shock_bp,
        "interpolation": interpolation,
        "price": p_mid,
        "price_rate_up": p_down,
        "price_rate_down": p_up,
        "effective_duration": float(duration),
        "effective_convexity": float(convexity),
        "note": "式 12.1/12.3：D=(P−−P+)/(2PΔr)，C=(P++P−−2P)/(PΔr²)，曲线平行 ±Δr 重定价",
    }


def dv01(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    curve: dict[float, float] | tuple[np.ndarray, np.ndarray],
    shock_bp: float = RATE_SHOCK_BP,
    interpolation: str = CURVE_INTERPOLATION,
) -> dict[str, Any]:
    """DV01 = 零息曲线平行 +1bp 的单位现金流价值变动（对称差分，书4 Ch12）。"""
    dr = shock_bp * 1e-4
    p_down = price_from_zero_curve(times, amounts, curve, +dr, interpolation)
    p_up = price_from_zero_curve(times, amounts, curve, -dr, interpolation)
    value = float((p_up - p_down) / (2.0 * shock_bp))
    return {
        "shock_bp": shock_bp,
        "interpolation": interpolation,
        "dv01": value,
        "note": "DV01 = (P(−1bp) − P(+1bp))/2，平行移动、对称差分（书4 Ch12）",
    }


def dv01_from_duration(value: float, modified_duration: float) -> dict[str, Any]:
    """DV01 = 市值 × Modified D × 1bp（书4 Ch12）。"""
    return {
        "value": value,
        "modified_duration": modified_duration,
        "dv01": value * modified_duration * 1e-4,
        "note": "DV01 = Value × Modified D × 0.0001（书4 Ch12）",
    }


def duration_from_dv01(dv01_value: float, value: float) -> dict[str, Any]:
    """D = 10,000 × DV01/Value（书4 Ch12，利率小数口径）。"""
    if value <= 0:
        raise ValueError("value must be > 0")
    return {
        "dv01": dv01_value,
        "value": value,
        "duration": 10000.0 * dv01_value / value,
        "note": "D = 10,000 × DV01/Value（书4 Ch12）",
    }


def portfolio_aggregate(positions: list[dict[str, float]]) -> dict[str, Any]:
    """组合聚合（书4 Ch12）：DV01 可加；duration/convexity 按市值加权。

    positions：每项 {"market_value", "duration", "convexity", "dv01"}，
    可带 "name"。市值权重 V_i/ΣV。
    """
    if not positions:
        raise ValueError("positions must be non-empty")
    values = np.array([float(p["market_value"]) for p in positions], dtype=float)
    total = float(values.sum())
    if total <= 0:
        raise ValueError("total market value must be > 0")
    weights = values / total
    durations = np.array([float(p["duration"]) for p in positions], dtype=float)
    convexities = np.array([float(p["convexity"]) for p in positions], dtype=float)
    dv01s = np.array([float(p["dv01"]) for p in positions], dtype=float)
    return {
        "n_positions": len(positions),
        "total_market_value": total,
        "dv01": float(dv01s.sum()),
        "duration": float(np.sum(weights * durations)),
        "convexity": float(np.sum(weights * convexities)),
        "weights": weights,
        "note": "书4 Ch12：DV01_P = Σ DV01_i；D_P = Σ(V_i/V)·D_i；C_P = Σ(V_i/V)·C_i",
    }


def dv01_hedge_face(portfolio_dv01: float, hedge_dv01_per_face: float) -> dict[str, Any]:
    """DV01 对冲配比：对冲工具面值 = 组合DV01 / 工具每面值DV01（书4 Ch12）。

    符号约定：返回使组合 DV01 归零的工具头寸面值（与组合 DV01 反号）。
    """
    if hedge_dv01_per_face == 0:
        raise ValueError("hedge_dv01_per_face must be non-zero")
    return {
        "portfolio_dv01": portfolio_dv01,
        "hedge_dv01_per_face": hedge_dv01_per_face,
        "hedge_face": -portfolio_dv01 / hedge_dv01_per_face,
        "note": "对冲工具 DV01 = −组合 DV01；面值 = 组合DV01/工具每面值DV01（负=做空，书4 Ch12）",
    }


def parallel_shift_approx(
    price: float,
    duration: float,
    convexity: float,
    delta_r: float,
) -> dict[str, Any]:
    """平行移动二阶近似 ΔP = −D·P·Δr + ½·C·P·(Δr)²（书4 Ch12 式 12.4）。"""
    if price <= 0:
        raise ValueError("price must be > 0")
    dp = -duration * price * delta_r + 0.5 * convexity * price * delta_r * delta_r
    return {
        "price": price,
        "duration": duration,
        "convexity": convexity,
        "delta_r": delta_r,
        "delta_price": float(dp),
        "new_price": float(price + dp),
        "note": "ΔP = −D·P·Δr + ½CP(Δr)²（式 12.4，Taylor 二阶近似）",
    }


def key_rate_shifts(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    curve: dict[float, float] | tuple[np.ndarray, np.ndarray],
    key_tenors: tuple[float, ...] = KEY_RATE_TENORS,
    shock_bp: float = RATE_SHOCK_BP,
    interpolation: str = CURVE_INTERPOLATION,
) -> dict[str, Any]:
    """Key rate 扭转 KR01（书4 Ch13）。

    每个关键利率节点做局部线性 shift（三角帽：该节点 +Δr，线性渐减到相邻
    节点为 0；首节点左侧、末节点右侧外延为常数 Δr），权重恒有 Σw_i(t)=1，
    故 ΣKR01 = DV01（自检恒等式，写入单测）。KR01_i = P_base − P(shift_i)。
    """
    if isinstance(curve, dict):
        curve_times = np.array(sorted(curve), dtype=float)
        curve_rates = np.array([curve[k] for k in sorted(curve)], dtype=float)
    else:
        curve_times = np.asarray(curve[0], dtype=float)
        curve_rates = np.asarray(curve[1], dtype=float)
    tenors = np.asarray(key_tenors, dtype=float)
    if tenors.ndim != 1 or len(tenors) < 2 or np.any(np.diff(tenors) <= 0):
        raise ValueError("key_tenors must be a strictly increasing sequence of length >= 2")
    dr = shock_bp * 1e-4
    # 三角帽权重：节点 k_i 处为 1，相邻节点处为 0，端点外延为常数
    left = np.concatenate(([tenors[0]], tenors[:-1]))
    right = np.concatenate((tenors[1:], [tenors[-1]]))
    weights = []
    for k, lo, hi in zip(tenors, left, right):
        w = np.zeros_like(curve_times)
        mid_lo = (curve_times >= lo) & (curve_times <= k)
        mid_hi = (curve_times >= k) & (curve_times <= hi)
        if k > lo:
            w[mid_lo] = (curve_times[mid_lo] - lo) / (k - lo)
        else:  # 首节点：左侧外延常数 1
            w[curve_times <= k] = 1.0
        if hi > k:
            w[mid_hi] = (hi - curve_times[mid_hi]) / (hi - k)
        else:  # 末节点：右侧外延常数 1
            w[curve_times >= k] = 1.0
        weights.append(w)
    weights_arr = np.vstack(weights)
    if not np.allclose(weights_arr.sum(axis=0), 1.0):
        raise AssertionError("key rate hat weights must sum to 1 at every pillar")
    t = np.asarray(times, dtype=float)
    cf = np.asarray(amounts, dtype=float)
    base_rates = interp_zero_rate((curve_times, curve_rates), t, interpolation)
    p_base = float(np.sum(cf * np.exp(-base_rates * t)))
    kr01s = []
    for i in range(len(tenors)):
        shifted_curve = curve_rates + weights_arr[i] * dr
        shifted_rates = interp_zero_rate((curve_times, shifted_curve), t, interpolation)
        p_shifted = float(np.sum(cf * np.exp(-shifted_rates * t)))
        kr01s.append((p_base - p_shifted) / shock_bp)
    kr01_arr = np.array(kr01s)
    # 自检：Σ shift = 平行移动 → ΣKR01 = DV01
    parallel = interp_zero_rate((curve_times, curve_rates + dr), t, interpolation)
    p_parallel = float(np.sum(cf * np.exp(-parallel * t)))
    dv01_value = (p_base - p_parallel) / shock_bp
    return {
        "key_tenors": tuple(float(k) for k in tenors),
        "shock_bp": shock_bp,
        "interpolation": interpolation,
        "price": p_base,
        "kr01": kr01_arr,
        "kr01_sum": float(kr01_arr.sum()),
        "dv01": float(dv01_value),
        "kr01_sum_matches_dv01": bool(np.isclose(kr01_arr.sum(), dv01_value, rtol=1e-4, atol=1e-12)),
        "note": "书4 Ch13：三角帽局部线性 shift（端点外延），Σw_i(t)=1 → ΣKR01=DV01 "
        "一阶自检（残差为价格对利率非线性的二阶项，rtol=1e-4）",
    }


def convertible_bond_floor(
    times: np.ndarray | list[float],
    amounts: np.ndarray | list[float],
    curve: dict[float, float] | tuple[np.ndarray, np.ndarray],
    credit_spread: float,
    shock_bp: float = RATE_SHOCK_BP,
    interpolation: str = CURVE_INTERPOLATION,
) -> dict[str, Any]:
    """可转债债底（纯债价值）：现金流按无风险曲线折现再乘信用因子 e^{−s·t}
    （书3 Ch16/17 落地提示：折现率 = 无风险 + 信用利差 s，连续复利口径）。

    spread duration（书3 Ch17）：利差 ±Δs 重定价的 effective duration，
    衡量债底对信用利差的敏感度。
    """
    t = np.asarray(times, dtype=float)
    cf = np.asarray(amounts, dtype=float)
    rates = interp_zero_rate(curve, t, interpolation)

    def _floor(spread: float) -> float:
        return float(np.sum(cf * np.exp(-(rates + spread) * t)))

    ds = shock_bp * 1e-4
    p_mid = _floor(credit_spread)
    p_down = _floor(credit_spread + ds)
    p_up = _floor(credit_spread - ds)
    if p_mid <= 0:
        raise ValueError("bond floor value must be > 0")
    spread_duration = (p_up - p_down) / (2.0 * p_mid * ds)
    return {
        "credit_spread": credit_spread,
        "shock_bp": shock_bp,
        "interpolation": interpolation,
        "pure_bond_value": p_mid,
        "value_spread_up": p_down,
        "value_spread_down": p_up,
        "spread_duration": float(spread_duration),
        "note": "债底 = Σ CF·e^{−(r(t)+s)·t}（无风险+信用利差，连续）；"
        "spread duration = 利差 ±1bp 重定价（书3 Ch17）",
    }
