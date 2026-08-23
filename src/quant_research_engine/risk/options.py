"""期权内核：BSM/Black's 定价、隐含波动率反解、CRR 二叉树（美式）、Greeks 全组。

- BSM（书4 Ch15 式 15.6–15.9）：无股息 c = S₀N(d1) − K·e^{−rT}N(d2)；
  连续股息率 q：S₀ 换 S₀·e^{−qT}、d1 中 r 换 r−q；离散股息修正：
  S₀ 换 S₀−D（D=期内股息 PV）。put-call parity 自检写入单测。
- Black's model（式 15.12/15.13，期货期权）：
  c = e^{−rT}[F₀N(d1) − K·N(d2)]，d1 = [ln(F₀/K) + σ²T/2]/(σ√T)。
- 隐含波动率（书4 Ch15）：无解析解，scipy.optimize.brentq 反解
  （教材惯例 successive bisection），区间集中参数 IV_BRACKET。
- CRR 二叉树（书4 Ch14 式 14.1–14.7）：u = e^{σ√Δt}，d = 1/u，
  p = (e^{(r−q)Δt} − d)/(u − d)；欧式 f = e^{−rΔt}[p·f_u + (1−p)·f_d]；
  美式每节点 max(行权价值, 持有价值) 回滚。树第一层两节点输出
  delta = (f_u − f_d)/(S·u − S·d)（式 14.1）。
- Greeks（书4 Ch16 式 16.1 + Table 16.2 含 q 版；期货期权 rho = −f·T）；
  组合 Greeks = 头寸加权和（数量×单值求和）。
- 美式期权 Greeks（书4 Ch16 方法）：二叉树数值差分——delta 用第一层
  两节点、gamma 用第二层两个 delta 差、theta 用隔层中节点时间差、
  vega/rho 微扰重建树（微扰步长集中参数 GREEK_SHOCK_SIGMA/RATE）。

纯函数零 DB；输入为调用方给定参数（S/K/T/σ/r/q），不读行情。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import optimize, stats

from quant_research_engine.risk.constants import (
    DEFAULT_TREE_STEPS,
    GREEK_SHOCK_RATE,
    GREEK_SHOCK_SIGMA,
    IV_BRACKET,
)

OPTION_TYPES = ("call", "put")


def _validate_common(S0: float, K: float, sigma: float, T: float) -> None:
    if S0 <= 0:
        raise ValueError("S0 must be > 0")
    if K <= 0:
        raise ValueError("K must be > 0")
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    if T <= 0:
        raise ValueError("T must be > 0")


def _d1_d2(S0: float, K: float, r: float, sigma: float, T: float, q: float) -> tuple[float, float]:
    """d1 = [ln(S₀/K) + (r − q + σ²/2)T]/(σ√T)；d2 = d1 − σ√T。"""
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma * sigma) * T) / sq
    return d1, d1 - sq


def bsm_price(
    S0: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    q: float = 0.0,
    option_type: str = "call",
    dividend_pv: float = 0.0,
) -> dict[str, Any]:
    """BSM 欧式定价（书4 Ch15 式 15.6–15.9）。

    连续股息率 q（式 15.8/15.9）；离散股息修正 dividend_pv=D 时以
    S₀−D 代入无股息公式（书4 Ch15 离散股息节）。两者可叠加
    （S_eff = S₀−D 之后再按 q 调整）。
    """
    _validate_common(S0, K, sigma, T)
    if option_type not in OPTION_TYPES:
        raise ValueError(f"option_type must be one of {OPTION_TYPES}")
    if dividend_pv < 0:
        raise ValueError("dividend_pv must be >= 0")
    s_eff = S0 - dividend_pv
    if s_eff <= 0:
        raise ValueError("S0 - dividend_pv must be > 0")
    d1, d2 = _d1_d2(s_eff, K, r, sigma, T, q)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)
    n1, n2 = stats.norm.cdf(d1), stats.norm.cdf(d2)
    if option_type == "call":
        price = s_eff * disc_q * n1 - K * disc_r * n2
    else:
        price = K * disc_r * (1.0 - n2) - s_eff * disc_q * (1.0 - n1)
    return {
        "model": "bsm",
        "S0": S0,
        "K": K,
        "r": r,
        "sigma": sigma,
        "T": T,
        "q": q,
        "dividend_pv": dividend_pv,
        "option_type": option_type,
        "d1": float(d1),
        "d2": float(d2),
        "price": float(price),
        "note": "式 15.6–15.9：c = S₀e^{−qT}N(d1) − Ke^{−rT}N(d2)；"
        "离散股息以 S₀−D 代入（书4 Ch15）",
    }


def black76_price(
    F0: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    option_type: str = "call",
) -> dict[str, Any]:
    """Black's model 期货期权定价（书4 Ch15 式 15.12/15.13）。"""
    _validate_common(F0, K, sigma, T)
    if option_type not in OPTION_TYPES:
        raise ValueError(f"option_type must be one of {OPTION_TYPES}")
    sq = sigma * math.sqrt(T)
    d1 = (math.log(F0 / K) + 0.5 * sigma * sigma * T) / sq
    d2 = d1 - sq
    disc = math.exp(-r * T)
    n1, n2 = stats.norm.cdf(d1), stats.norm.cdf(d2)
    if option_type == "call":
        price = disc * (F0 * n1 - K * n2)
    else:
        price = disc * (K * (1.0 - n2) - F0 * (1.0 - n1))
    return {
        "model": "black76",
        "F0": F0,
        "K": K,
        "r": r,
        "sigma": sigma,
        "T": T,
        "option_type": option_type,
        "d1": float(d1),
        "d2": float(d2),
        "price": float(price),
        "note": "式 15.12/15.13：c = e^{−rT}[F₀N(d1) − KN(d2)]（期货期权）",
    }


def implied_vol(
    price: float,
    S0: float,
    K: float,
    r: float,
    T: float,
    option_type: str = "call",
    q: float = 0.0,
    dividend_pv: float = 0.0,
    bracket: tuple[float, float] = IV_BRACKET,
) -> dict[str, Any]:
    """隐含波动率反解（书4 Ch15：无解析解，迭代求解；brentq，区间 IV_BRACKET）。"""
    if price <= 0:
        raise ValueError("price must be > 0")
    if option_type not in OPTION_TYPES:
        raise ValueError(f"option_type must be one of {OPTION_TYPES}")
    lo, hi = bracket

    def _gap(sig: float) -> float:
        return bsm_price(S0, K, r, sig, T, q, option_type, dividend_pv)["price"] - price

    f_lo, f_hi = _gap(lo), _gap(hi)
    if f_lo * f_hi > 0:
        raise ValueError(f"implied vol not bracketed in {bracket}: f(lo)={f_lo:.6g}, f(hi)={f_hi:.6g}")
    iv = float(optimize.brentq(_gap, lo, hi))
    return {
        "method": "brentq",
        "bracket": bracket,
        "S0": S0,
        "K": K,
        "r": r,
        "T": T,
        "q": q,
        "dividend_pv": dividend_pv,
        "option_type": option_type,
        "price": price,
        "implied_vol": iv,
        "note": "书4 Ch15：无解析解，brentq 反解（教材惯例 successive bisection）",
    }


def crr_tree(
    S0: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    n_steps: int = DEFAULT_TREE_STEPS,
    q: float = 0.0,
    option_type: str = "call",
    american: bool = False,
    return_grid: bool = False,
) -> dict[str, Any]:
    """CRR 二叉树定价（书4 Ch14 式 14.1–14.7）。

    u = e^{σ√Δt}、d = e^{−σ√Δt}、p = (e^{(r−q)Δt} − d)/(u − d)；
    欧式 backward induction；美式每节点 max(行权, 持有)。
    输出树第一层 delta = (f_u − f_d)/(S₀u − S₀d)（式 14.1）。
    return_grid=True 时附完整节点价值网格（行=时间步，列=节点）与
    美式提前行权标记网格，供对教材节点值/诊断使用（大步数慎用内存）。
    """
    _validate_common(S0, K, sigma, T)
    if option_type not in OPTION_TYPES:
        raise ValueError(f"option_type must be one of {OPTION_TYPES}")
    if n_steps < 2:
        raise ValueError("n_steps must be >= 2")
    dt = T / n_steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    a = math.exp((r - q) * dt)
    p = (a - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError(f"risk-neutral p out of (0,1): {p:.6g}（增大 n_steps 或检查参数）")
    disc = math.exp(-r * dt)
    # 末端标的价格与 payoff
    j = np.arange(n_steps + 1)
    s_end = S0 * u ** j * d ** (n_steps - j)
    if option_type == "call":
        values = np.maximum(s_end - K, 0.0)
    else:
        values = np.maximum(K - s_end, 0.0)
    grid = [values] if return_grid else None
    exercise_grid = None
    if return_grid and american:
        exercise_grid = [np.zeros(n_steps + 1, dtype=bool)]
    first_layer: np.ndarray | None = None
    for step in range(n_steps - 1, -1, -1):
        s_node = S0 * u ** np.arange(step + 1) * d ** (step - np.arange(step + 1))
        hold = disc * (p * values[1:] + (1.0 - p) * values[:-1])
        if american:
            if option_type == "call":
                intrinsic = np.maximum(s_node - K, 0.0)
            else:
                intrinsic = np.maximum(K - s_node, 0.0)
            if exercise_grid is not None:
                exercise_grid.insert(0, intrinsic > hold)
            values = np.maximum(hold, intrinsic)
        else:
            values = hold
        if step == 1:
            first_layer = values.copy()
        if grid is not None:
            grid.insert(0, values)
    price = float(values[0])
    # 第一层 delta（式 14.1）：Δ = (f_u − f_d)/(S₀u − S₀d)
    s_up = S0 * u
    s_dn = S0 * d
    if grid is not None:
        f_u, f_d = float(grid[1][1]), float(grid[1][0])
    else:
        assert first_layer is not None
        f_u, f_d = float(first_layer[1]), float(first_layer[0])
    delta = (f_u - f_d) / (s_up - s_dn)
    result: dict[str, Any] = {
        "model": "crr",
        "S0": S0,
        "K": K,
        "r": r,
        "sigma": sigma,
        "T": T,
        "q": q,
        "option_type": option_type,
        "american": american,
        "n_steps": n_steps,
        "dt": dt,
        "u": u,
        "d": d,
        "p": float(p),
        "price": price,
        "delta": float(delta),
        "note": "式 14.4–14.7：u=e^{σ√Δt}，d=1/u，p=(e^{(r−q)Δt}−d)/(u−d)；"
        "美式每节点 max(行权,持有)；delta 用第一层两节点（式 14.1）",
    }
    if grid is not None:
        result["grid"] = grid
    if exercise_grid is not None:
        result["exercise_grid"] = exercise_grid
    return result


def bsm_greeks(
    S0: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    q: float = 0.0,
    option_type: str = "call",
    dividend_pv: float = 0.0,
) -> dict[str, Any]:
    """BSM Greeks 全组解析解（书4 Ch16 式 16.1 + Table 16.2 含 q 版）。

    Δc = e^{−qT}N(d1)，Δp = e^{−qT}(N(d1)−1)；
    Γ = N′(d1)e^{−qT}/(S₀σ√T)；vega = S₀√T·N′(d1)e^{−qT}（σ 小数口径，
    每 1% 波动率变动 ≈ vega×0.01）；theta 含 ±qS·N(±d1)e^{−qT} 项；
    ρc = KTe^{−rT}N(d2)，ρp = −KTe^{−rT}N(−d2)。
    theta 为年口径（每日时间衰减 = theta/年天数由调用方按口径换算）。
    """
    _validate_common(S0, K, sigma, T)
    if option_type not in OPTION_TYPES:
        raise ValueError(f"option_type must be one of {OPTION_TYPES}")
    if dividend_pv != 0.0:
        raise ValueError("bsm_greeks 不处理离散股息，请用 S0−D 作为 S0 调用")
    sq = math.sqrt(T)
    d1, d2 = _d1_d2(S0, K, r, sigma, T, q)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)
    n1, n2 = stats.norm.cdf(d1), stats.norm.cdf(d2)
    np1 = float(stats.norm.pdf(d1))
    gamma = np1 * disc_q / (S0 * sigma * sq)
    vega = S0 * sq * np1 * disc_q
    if option_type == "call":
        delta = disc_q * n1
        theta = (-S0 * np1 * sigma * disc_q / (2.0 * sq) - r * K * disc_r * n2
                 + q * S0 * n1 * disc_q)
        rho = K * T * disc_r * n2
    else:
        delta = disc_q * (n1 - 1.0)
        theta = (-S0 * np1 * sigma * disc_q / (2.0 * sq) + r * K * disc_r * (1.0 - n2)
                 - q * S0 * (1.0 - n1) * disc_q)
        rho = -K * T * disc_r * (1.0 - n2)
    return {
        "model": "bsm",
        "S0": S0,
        "K": K,
        "r": r,
        "sigma": sigma,
        "T": T,
        "q": q,
        "option_type": option_type,
        "delta": float(delta),
        "gamma": float(gamma),
        "vega": float(vega),
        "theta": float(theta),
        "rho": float(rho),
        "note": "式 16.1 + Table 16.2（含 q 版）；自检恒等式 θ + rSΔ + ½σ²S²Γ = rf"
        "（式 16.2）写入单测",
    }


def black76_greeks(
    F0: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    option_type: str = "call",
) -> dict[str, Any]:
    """Black's model 期货期权 Greeks（书4 Ch16 Table 16.2 期货期权版）。

    Δc = e^{−rT}N(d1)；Γ = e^{−rT}N′(d1)/(F₀σ√T)；vega = F₀√T·N′(d1)e^{−rT}；
    θc = r·c − F₀e^{−rT}N′(d1)σ/(2√T)（call；put 同号时间项 + r·p 结构）；
    ρ = −f·T（f=期权价格）。
    """
    _validate_common(F0, K, sigma, T)
    if option_type not in OPTION_TYPES:
        raise ValueError(f"option_type must be one of {OPTION_TYPES}")
    sq = math.sqrt(T)
    d1 = (math.log(F0 / K) + 0.5 * sigma * sigma * T) / (sigma * sq)
    d2 = d1 - sigma * sq
    disc = math.exp(-r * T)
    n1, n2 = stats.norm.cdf(d1), stats.norm.cdf(d2)
    np1 = float(stats.norm.pdf(d1))
    gamma = disc * np1 / (F0 * sigma * sq)
    vega = F0 * sq * np1 * disc
    price = black76_price(F0, K, r, sigma, T, option_type)["price"]
    time_decay = -F0 * disc * np1 * sigma / (2.0 * sq)
    if option_type == "call":
        delta = disc * n1
    else:
        delta = -disc * (1.0 - n1)
    # θ = −∂f/∂T = r·f − F₀e^{−rT}N′(d1)σ/(2√T)（call/put 同一形式，
    # 利用 F₀N′(d1)=KN′(d2) 恒等式化简）
    theta = time_decay + r * price
    rho = -price * T
    return {
        "model": "black76",
        "F0": F0,
        "K": K,
        "r": r,
        "sigma": sigma,
        "T": T,
        "option_type": option_type,
        "price": float(price),
        "delta": float(delta),
        "gamma": float(gamma),
        "vega": float(vega),
        "theta": float(theta),
        "rho": float(rho),
        "note": "Table 16.2 期货期权版：Δc=e^{−rT}N(d1)，ρ=−f·T",
    }


def american_greeks_numeric(
    S0: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    n_steps: int = DEFAULT_TREE_STEPS,
    q: float = 0.0,
    option_type: str = "call",
    shock_sigma: float = GREEK_SHOCK_SIGMA,
    shock_rate: float = GREEK_SHOCK_RATE,
) -> dict[str, Any]:
    """美式期权 Greeks：CRR 二叉树数值差分（书4 Ch16 方法）。

    delta 用第一层两节点；gamma 用第二层两个 delta 差；
    theta 用隔层（步 0 与步 2）中节点时间差；vega/rho 微扰 ±h 重建树。
    """
    _validate_common(S0, K, sigma, T)
    base = crr_tree(S0, K, r, sigma, T, n_steps, q, option_type, american=True, return_grid=True)
    grid = base["grid"]
    dt = base["dt"]
    u, d = base["u"], base["d"]
    # delta（第一层）
    f_u, f_d = float(grid[1][1]), float(grid[1][0])
    delta = (f_u - f_d) / (S0 * u - S0 * d)
    # gamma（第二层两个 delta 差）
    f_uu, f_ud, f_dd = float(grid[2][2]), float(grid[2][1]), float(grid[2][0])
    d_up = (f_uu - f_ud) / (S0 * u * u - S0)  # 第二层上侧 delta（S·u² vs S·u·d=S）
    d_dn = (f_ud - f_dd) / (S0 - S0 * d * d)
    gamma = (d_up - d_dn) / (0.5 * (S0 * u * u + S0) - 0.5 * (S0 + S0 * d * d))
    # theta（隔层中节点：步 2 中节点价格 vs 步 0，时间差 2Δt）
    theta = (float(grid[2][1]) - float(grid[0][0])) / (2.0 * dt)
    # vega / rho（微扰重建树）
    v_up = crr_tree(S0, K, r, sigma + shock_sigma, T, n_steps, q, option_type, american=True)["price"]
    v_dn = crr_tree(S0, K, r, sigma - shock_sigma, T, n_steps, q, option_type, american=True)["price"]
    vega = (v_up - v_dn) / (2.0 * shock_sigma)
    r_up = crr_tree(S0, K, r + shock_rate, sigma, T, n_steps, q, option_type, american=True)["price"]
    r_dn = crr_tree(S0, K, r - shock_rate, sigma, T, n_steps, q, option_type, american=True)["price"]
    rho = (r_up - r_dn) / (2.0 * shock_rate)
    return {
        "model": "crr_numeric",
        "S0": S0,
        "K": K,
        "r": r,
        "sigma": sigma,
        "T": T,
        "q": q,
        "option_type": option_type,
        "n_steps": n_steps,
        "shock_sigma": shock_sigma,
        "shock_rate": shock_rate,
        "price": base["price"],
        "delta": float(delta),
        "gamma": float(gamma),
        "vega": float(vega),
        "theta": float(theta),
        "rho": float(rho),
        "note": "书4 Ch16：delta 第一层两节点、gamma 第二层两个 delta 差、"
        "theta 隔层中节点、vega/rho ±h 微扰重建树",
    }


def portfolio_greeks(positions: list[dict[str, float]]) -> dict[str, Any]:
    """组合 Greeks = 头寸加权和（书4 Ch16：数量×单值求和）。

    positions：每项 {"quantity", "delta", "gamma", "vega", "theta", "rho"}，
    可带 "name"。quantity 正=多头、负=空头。
    """
    if not positions:
        raise ValueError("positions must be non-empty")
    qty = np.array([float(p["quantity"]) for p in positions], dtype=float)
    out: dict[str, Any] = {"n_positions": len(positions), "quantities": qty}
    for greek in ("delta", "gamma", "vega", "theta", "rho"):
        vals = np.array([float(p[greek]) for p in positions], dtype=float)
        out[greek] = float(np.sum(qty * vals))
    out["note"] = "书4 Ch16：组合 Greeks = Σ 数量×单值（可加性）"
    return out
