"""Delta-Gamma-Vega 近似组合 VaR（书4 Ch16 + Ch2）。

组合 P&L 二阶近似（式 2.3 加 vega 项）：

    ΔV ≈ Δ·δS + ½·Γ·(δS)² + vega·δσ

风险因子假设：δS ~ N(0, sS²)、δσ ~ N(0, sσ²)，相互独立（相关性参数化
留待多因子协方差扩展，当前版本披露 rho=0 假设）。

解析矩（二次型的非中心卡方表示）：令 a = Δ·sS、b = ½·Γ·sS²、
c = vega·sσ，则 ΔV = a·Z + b·Z² + c·W（Z,W 独立标准正态）
= b·χ²₁(λ) − bλ + c·W，λ = a²/(4b²)。非中心卡方 χ²₁(λ) 的累积量
κ_r = 2^{r−1}(r−1)!·(1+rλ)·b^r（r≥1），vega 项只进 κ2。由此得
P&L 的均值/方差/偏度/超额峰度的解析式，VaR 分位用正态或
Cornish-Fisher 展开（摘要声明教材章节未点名 Cornish-Fisher，此处按
业界标准实现并如实标注；CF 仅在偏度适中时有效，高偏度如纯 gamma
χ² 型 P&L 下分位失真，为已知限制——测试中对解析矩（不依赖 CF）
做 delta 中性纯 gamma 核对）。

定位（CR §7）：本模块是「适配器」而非新 VaR 引擎——只生成 VaR 分位/
序列，统计回测完全复用 backtest_var.backtest_var_summary（HIT/LR）。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from quant_research_engine.risk.constants import z_value

DGV_METHODS = ("normal", "cornish_fisher")


def dgv_pnl(
    delta: float,
    gamma: float,
    vega: float,
    delta_S: float | np.ndarray,
    delta_sigma: float | np.ndarray = 0.0,
) -> np.ndarray:
    """组合 P&L 二阶近似：ΔV ≈ Δ·δS + ½Γ(δS)² + vega·δσ（书4 Ch2 式 2.3 + Ch16 vega 项）。

    delta_S 为标的价格绝对变动，delta_sigma 为波动率绝对变动（小数）。
    支持标量或等长数组（逐情景），返回 ndarray。
    """
    dS = np.asarray(delta_S, dtype=float)
    dsig = np.asarray(delta_sigma, dtype=float)
    return delta * dS + 0.5 * gamma * dS * dS + vega * dsig


def dgv_var(
    delta: float,
    gamma: float,
    vega: float,
    spot_shock_sd: float,
    vol_shock_sd: float = 0.0,
    confidence: float = 0.99,
    method: str = "normal",
) -> dict[str, Any]:
    """DGV 近似组合 VaR（损失取正号，与 tail.py/backtest_var.py 同口径）。

    输入组合 Greeks（delta/gamma/vega）与风险因子日变动标准差
    spot_shock_sd（δS 的 sd，价格单位）/vol_shock_sd（δσ 的 sd，
    波动率小数单位，0 = 忽略波动率风险）。

    返回 P&L 解析矩（均值/方差/偏度/超额峰度）与 VaR 分位：
    - normal：VaR = μ_L + σ_L·z；
    - cornish_fisher：w = z + (z²−1)/6·S_L + (z³−3z)/24·K_ex −
      (2z³−5z)/36·S_L²（S_L = 损失偏度 = −P&L 偏度）。
    """
    if spot_shock_sd <= 0:
        raise ValueError("spot_shock_sd must be > 0")
    if vol_shock_sd < 0:
        raise ValueError("vol_shock_sd must be >= 0")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if method not in DGV_METHODS:
        raise ValueError(f"method must be one of {DGV_METHODS}")
    a = delta * spot_shock_sd
    b = 0.5 * gamma * spot_shock_sd * spot_shock_sd
    c = vega * vol_shock_sd
    if b != 0.0:
        lam = a * a / (4.0 * b * b)
        k2 = 2.0 * b * b * (1.0 + 2.0 * lam) + c * c
        k3 = 8.0 * b**3 * (1.0 + 3.0 * lam)
        k4 = 48.0 * b**4 * (1.0 + 4.0 * lam)
    else:  # 纯线性 + vega：正态
        k2 = a * a + c * c
        k3 = 0.0
        k4 = 0.0
    mean_pnl = b  # E[ΔV] = ½Γ·sS²
    var_pnl = k2
    sd_pnl = math.sqrt(k2)
    skew_pnl = k3 / k2**1.5 if k2 > 0 else 0.0
    ex_kurt = k4 / (k2 * k2) if k2 > 0 else 0.0
    # 损失 L = −ΔV：均值反号、偏度反号、峰度不变
    mean_loss = -mean_pnl
    skew_loss = -skew_pnl
    z = z_value(confidence)
    if method == "normal":
        w = z
    else:
        w = (z + (z * z - 1.0) / 6.0 * skew_loss + (z**3 - 3.0 * z) / 24.0 * ex_kurt
             - (2.0 * z**3 - 5.0 * z) / 36.0 * skew_loss * skew_loss)
    var = mean_loss + sd_pnl * w
    return {
        "method": method,
        "confidence": confidence,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "spot_shock_sd": spot_shock_sd,
        "vol_shock_sd": vol_shock_sd,
        "mean_pnl": float(mean_pnl),
        "var_pnl": float(var_pnl),
        "sd_pnl": float(sd_pnl),
        "skew_pnl": float(skew_pnl),
        "excess_kurtosis_pnl": float(ex_kurt),
        "z": float(z),
        "adjusted_quantile": float(w),
        "var": float(var),
        "note": "ΔV ≈ Δ·δS + ½Γ(δS)² + vega·δσ（式 2.3 + vega 项）；δS/δσ 独立正态"
        "（rho=0 假设披露）；矩为非中心卡方累积量解析式；损失取正号。"
        "Cornish-Fisher 展开为业界标准（摘要声明教材章节未点名），如实标注",
    }


def dgv_var_series(
    frame: pd.DataFrame,
    confidence: float = 0.99,
    method: str = "normal",
) -> pd.Series:
    """逐日 DGV VaR 序列（适配器）：直接喂 backtest_var.backtest_var_summary。

    frame 每行一日，必备列 delta/gamma/vega/spot_shock_sd，可选列
    vol_shock_sd（缺省 0）。返回与 frame 同索引的 VaR 序列（损失正号），
    与既有 hit_series(returns, var_series) 的收益序列按索引对齐即可复用
    HIT/覆盖率 LR/独立性回测（本模块不新造回测引擎）。
    """
    required = {"delta", "gamma", "vega", "spot_shock_sd"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"frame missing columns: {sorted(missing)}")
    vol_sd = frame["vol_shock_sd"] if "vol_shock_sd" in frame.columns else pd.Series(0.0, index=frame.index)
    out = []
    for (idx, row), v_sd in zip(frame.iterrows(), vol_sd):
        res = dgv_var(
            float(row["delta"]),
            float(row["gamma"]),
            float(row["vega"]),
            float(row["spot_shock_sd"]),
            float(v_sd),
            confidence=confidence,
            method=method,
        )
        out.append(res["var"])
    return pd.Series(out, index=frame.index, name="dgv_var")
