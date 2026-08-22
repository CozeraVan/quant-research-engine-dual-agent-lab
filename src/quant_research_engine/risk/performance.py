"""绩效风险指标（书1 Ch5）：Sharpe/Treynor/Sortino/IR/Jensen's α。

- Sharpe：与引擎 portfolio/risk.py 完全同口径——
  ``mean(r − rf/252)/std(ddof=1) · √252``。
- Sortino：SR = (R_p − T)/√(E[min(0, R_pt − T)²])，日频 T 默认 rf/252，
  年化 ×√252（书1 Ch5 公式，年化按书2 Ch5 惯例）。
- Treynor：TPI = (E[R] − r)/β，E[R] 取日均 ×252 年化；β=cov(R_i,R_M)/σ²_M
  （式 5.1）。
- Tracking error / IR：TE = std(R_p − R_b)；IR = mean(active)/TE · √252。
- Jensen's α：市场模型回归 (R_p − r) = α + β(R_M − r) + ε（式 5.5）的截距，
  日频 α 与 ×252 年化均报。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from quant_research_engine.risk.constants import ANNUALIZATION_FACTOR, DEFAULT_RISK_FREE_RATE

_MIN_OBS = 2


def _clean(returns: pd.Series | np.ndarray | list[float]) -> pd.Series:
    series = pd.Series(returns, dtype=float).dropna()
    if len(series) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} non-NaN returns, got {len(series)}")
    return series


def _aligned(
    returns: pd.Series | np.ndarray | list[float],
    other: pd.Series | np.ndarray | list[float],
) -> tuple[pd.Series, pd.Series]:
    frame = pd.DataFrame({"r": pd.Series(returns, dtype=float), "m": pd.Series(other, dtype=float)}).dropna()
    if len(frame) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} paired non-NaN observations, got {len(frame)}")
    return frame["r"], frame["m"]


def beta(
    returns: pd.Series | np.ndarray | list[float],
    market: pd.Series | np.ndarray | list[float],
) -> float:
    """β = cov(R_i, R_M)/σ²_M（书1 Ch5 式 5.1）。"""
    r, m = _aligned(returns, market)
    market_var = float(m.var(ddof=1))
    if market_var <= 0:
        raise ValueError("market variance must be > 0")
    return float(np.cov(r, m, ddof=1)[0, 1] / market_var)


def sharpe_ratio(
    returns: pd.Series | np.ndarray | list[float],
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """Sharpe = mean(r − rf/252)/std · √252（与 portfolio/risk.py 同口径）。"""
    r = _clean(returns)
    daily_rf = risk_free_rate / annualization_factor
    std = float(r.std(ddof=1))
    sharpe = None
    if std > 0:
        sharpe = float(((r - daily_rf).mean() / std) * annualization_factor**0.5)
    return {
        "sharpe": sharpe,
        "risk_free_rate_annual": risk_free_rate,
        "annualization_factor": annualization_factor,
        "daily_mean_excess": float((r - daily_rf).mean()),
        "daily_std": std,
        "n_obs": int(len(r)),
        "note": "SPI=(E[R]−r)/σ（书1 Ch5）；日频口径与引擎 portfolio/risk.py 一致",
    }


def sortino_ratio(
    returns: pd.Series | np.ndarray | list[float],
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    target: float | None = None,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """Sortino = (R_p − T)/downside dev，年化 ×√252（书1 Ch5）。"""
    r = _clean(returns)
    daily_target = target if target is not None else risk_free_rate / annualization_factor
    shortfall = np.minimum(0.0, r.to_numpy() - daily_target)
    downside_dev = float(np.sqrt(np.mean(shortfall**2)))
    sortino = None
    if downside_dev > 0:
        sortino = float((r.mean() - daily_target) / downside_dev * annualization_factor**0.5)
    return {
        "sortino": sortino,
        "daily_target": daily_target,
        "daily_downside_deviation": downside_dev,
        "risk_free_rate_annual": risk_free_rate,
        "annualization_factor": annualization_factor,
        "n_obs": int(len(r)),
        "note": "SR=(R_p−T)/√(E[min(0,R_pt−T)²])（书1 Ch5）；T 默认 rf/252（MAR 口径）",
    }


def treynor_ratio(
    returns: pd.Series | np.ndarray | list[float],
    market: pd.Series | np.ndarray | list[float],
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """Treynor = (E[R] − r)/β，E[R] 日均 ×252 年化（书1 Ch5）。"""
    r, m = _aligned(returns, market)
    b = beta(r, m)
    treynor = None
    if b != 0:
        treynor = float((r.mean() * annualization_factor - risk_free_rate) / b)
    return {
        "treynor": treynor,
        "beta": b,
        "annualized_mean_return": float(r.mean() * annualization_factor),
        "risk_free_rate_annual": risk_free_rate,
        "annualization_factor": annualization_factor,
        "n_obs": int(len(r)),
        "note": "TPI=(E[R]−r)/β（书1 Ch5，适用于充分分散组合）；β=cov/σ²_M（式 5.1）",
    }


def information_ratio(
    returns: pd.Series | np.ndarray | list[float],
    benchmark: pd.Series | np.ndarray | list[float],
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """TE = std(R_p − R_b)；IR = mean(active)/TE · √252（书1 Ch5）。"""
    r, b = _aligned(returns, benchmark)
    active = r - b
    te = float(active.std(ddof=1))
    ir = None
    if te > 0:
        ir = float(active.mean() / te * annualization_factor**0.5)
    return {
        "information_ratio": ir,
        "tracking_error_daily": te,
        "tracking_error_annual": te * annualization_factor**0.5,
        "mean_active_return_daily": float(active.mean()),
        "annualization_factor": annualization_factor,
        "n_obs": int(len(active)),
        "note": "TE=std(R_p−R_b)；IR=平均 active return/TE（书1 Ch5）",
    }


def jensens_alpha(
    returns: pd.Series | np.ndarray | list[float],
    market: pd.Series | np.ndarray | list[float],
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """Jensen's α：市场模型 (R_p − r) = α + β(R_M − r) + ε 的截距（式 5.5）。"""
    r, m = _aligned(returns, market)
    daily_rf = risk_free_rate / annualization_factor
    excess_r = r - daily_rf
    excess_m = m - daily_rf
    regression = stats.linregress(excess_m, excess_r)
    alpha_daily = float(regression.intercept)
    return {
        "alpha_daily": alpha_daily,
        "alpha_annual": alpha_daily * annualization_factor,
        "beta": float(regression.slope),
        "r_squared": float(regression.rvalue**2),
        "p_value": float(regression.pvalue),
        "risk_free_rate_annual": risk_free_rate,
        "annualization_factor": annualization_factor,
        "n_obs": int(len(r)),
        "note": "市场模型回归截距（书1 Ch5 式 5.5）；日频 α 与 ×252 年化均报",
    }


def performance_summary(
    returns: pd.Series | np.ndarray | list[float],
    benchmark: pd.Series | np.ndarray | list[float] | None = None,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """绩效指标汇总；benchmark=None 时基准相关键为 null 而不报错。"""
    r = _clean(returns)
    summary: dict[str, Any] = {
        "sharpe": sharpe_ratio(r, risk_free_rate, annualization_factor),
        "sortino": sortino_ratio(r, risk_free_rate, None, annualization_factor),
        "beta": None,
        "treynor": None,
        "information_ratio": None,
        "jensens_alpha": None,
        "annualization_factor": annualization_factor,
        "risk_free_rate_annual": risk_free_rate,
        "n_obs": int(len(r)),
    }
    if benchmark is not None:
        _, m = _aligned(r, benchmark)
        summary["beta"] = beta(r, m)
        summary["treynor"] = treynor_ratio(r, m, risk_free_rate, annualization_factor)
        summary["information_ratio"] = information_ratio(r, m, annualization_factor)
        summary["jensens_alpha"] = jensens_alpha(r, m, risk_free_rate, annualization_factor)
    return summary
