"""压力测试（书4 Ch8）：历史情景回放、reverse stress、相关性崩溃提示。

- 历史情景库（constants.HISTORICAL_SCENARIOS）：2015 股灾、2018 单边熊、
  2020 疫情、2024 小微盘流动性危机；窗口参数化可增删（情景只存日期窗口
  常量，不提供行情数据——回放输入由调用方给）。
- 情景回放：给定策略逐日收益与情景窗口，计算窗口内累计损失
  1−Π(1+r_t)、峰谷（窗口内净值最大回撤，损失口径）、与当前 VaR/ES 的
  比值（Peak/VaR、Peak/ES，无量纲；参考 var-backtesting 口径）；有基准时
  附基准窗口累计收益与相关性崩溃对比（窗口内 vs 窗口外 Pearson 相关，
  呼应书1 Ch9 LTCM 红线「压力期相关性→1」）。
- reverse stress：给定亏损阈值，按 β 穿透（策略损失 ≈ β × 市场冲击）反推
  所需市场冲击 S* = 阈值/β，并在基准 h 日滚动累计收益分布上给出经验分位
  （历史窗口中跌得比 S* 更深的占比）与 σ 倍数。β≤0 时无法穿透，报错
  （策略与市场反向/无关时「市场冲击」不构成威胁通道，需假设性情景）。

压力测试是前瞻性 What-if 工具，不给概率分布；历史情景无法回测（书4 Ch8）。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.risk.constants import (
    HISTORICAL_SCENARIOS,
    REVERSE_STRESS_HORIZON,
)

_MIN_OBS = 2


def _clean(series: pd.Series | np.ndarray | list[float]) -> pd.Series:
    s = pd.Series(series, dtype=float).dropna()
    if len(s) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} non-NaN returns, got {len(s)}")
    return s


def _slice_window(series: pd.Series, window: tuple[str, str]) -> pd.Series:
    """按日期闭区间切片；非日期索引退化为位置切片（披露在返回值）。"""
    start, end = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    if isinstance(series.index, pd.DatetimeIndex):
        sliced = series.loc[(series.index >= start) & (series.index <= end)]
        return sliced.dropna()
    raise ValueError("series index must be DatetimeIndex for scenario window slicing")


def _max_drawdown_loss(returns: pd.Series) -> float:
    """窗口内净值曲线峰谷回撤（损失口径，正数）：1 − min_t(V_t / max_{s≤t} V_s)。"""
    nav = (1.0 + returns).cumprod()
    peak = nav.cummax()
    drawdown = 1.0 - nav / peak
    return float(drawdown.max())


def list_scenarios() -> dict[str, dict[str, str]]:
    """历史情景库清单（书4 Ch8 historical scenarios，A 股）。"""
    return {
        name: {"start": start, "end": end, "description": desc}
        for name, (start, end, desc) in HISTORICAL_SCENARIOS.items()
    }


def replay_scenario(
    strategy_returns: pd.Series | np.ndarray | list[float],
    window: tuple[str, str],
    benchmark_returns: pd.Series | np.ndarray | list[float] | None = None,
    var: float | None = None,
    es: float | None = None,
) -> dict[str, Any]:
    """历史情景回放（书4 Ch8）：窗口内策略累计损失、峰谷、Peak/VaR 比值。

    - strategy_returns / benchmark_returns 需 DatetimeIndex 逐日 simple 收益。
    - window = (start, end) 闭区间；与序列实际交易日取交集。
    - var / es：当前 1 日 VaR/ES（损失口径正数，如 R1 tail 模块输出），
      用于 Peak/VaR、Peak/ES 无量纲比值；None 时对应键为 null。
    - 有基准时输出窗口内/窗口外 Pearson 相关及 delta（相关性崩溃提示）。
    """
    r = _clean(strategy_returns)
    r_win = _slice_window(r, window)
    if len(r_win) < 1:
        raise ValueError(f"no strategy observations in window {window}")

    cumulative_return = float((1.0 + r_win).prod() - 1.0)
    cumulative_loss = -cumulative_return
    peak_trough = _max_drawdown_loss(r_win)

    result: dict[str, Any] = {
        "window": {"start": window[0], "end": window[1]},
        "n_days": int(len(r_win)),
        "strategy_cumulative_return": cumulative_return,
        "strategy_cumulative_loss": cumulative_loss,
        "strategy_peak_trough_drawdown": peak_trough,
        "var": var,
        "es": es,
        "peak_to_var": (peak_trough / var) if var else None,
        "peak_to_es": (peak_trough / es) if es else None,
        "note": "累计损失=1−Π(1+r)；峰谷=窗口内净值最大回撤（损失口径）；"
        "Peak/VaR 无量纲（VaR 为 1 日口径，比值度量情景峰谷覆盖几倍日度 VaR）",
    }

    if benchmark_returns is not None:
        b = _clean(benchmark_returns)
        b_win = _slice_window(b, window)
        aligned_win = pd.DataFrame({"r": r, "b": b}).loc[r_win.index].dropna()
        r_out = r.drop(index=r_win.index, errors="ignore")
        b_out = b.drop(index=b_win.index, errors="ignore")
        aligned_out = pd.DataFrame({"r": r_out, "b": b_out}).dropna()
        corr_win = (
            float(aligned_win["r"].corr(aligned_win["b"])) if len(aligned_win) >= _MIN_OBS else None
        )
        corr_out = (
            float(aligned_out["r"].corr(aligned_out["b"])) if len(aligned_out) >= _MIN_OBS else None
        )
        delta = (
            corr_win - corr_out if (corr_win is not None and corr_out is not None) else None
        )
        result["benchmark_cumulative_return"] = (
            float((1.0 + b_win).prod() - 1.0) if len(b_win) > 0 else None
        )
        result["correlation_breakdown"] = {
            "corr_in_window": corr_win,
            "corr_outside_window": corr_out,
            "delta": delta,
            "elevated": bool(delta is not None and delta > 0.0),
            "note": "窗口内 vs 窗口外 Pearson 相关；压力期相关性上升（→1）是"
            " LTCM 红线（书1 Ch9），分散假象需按压力态相关性重估",
        }
    return result


def replay_historical_scenarios(
    strategy_returns: pd.Series | np.ndarray | list[float],
    benchmark_returns: pd.Series | np.ndarray | list[float] | None = None,
    var: float | None = None,
    es: float | None = None,
    scenarios: dict[str, tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """批量回放历史情景库；样本不覆盖窗口的情景记 error 而不抛异常。"""
    library = scenarios if scenarios is not None else HISTORICAL_SCENARIOS
    out: dict[str, Any] = {}
    for name, (start, end, desc) in library.items():
        try:
            entry = replay_scenario(strategy_returns, (start, end), benchmark_returns, var, es)
            entry["description"] = desc
            out[name] = entry
        except ValueError as exc:
            out[name] = {"description": desc, "error": str(exc)}
    return out


def reverse_stress(
    strategy_returns: pd.Series | np.ndarray | list[float],
    benchmark_returns: pd.Series | np.ndarray | list[float],
    loss_threshold: float,
    horizon: int = REVERSE_STRESS_HORIZON,
) -> dict[str, Any]:
    """Reverse stress（书4 Ch8）：给定亏损阈值反查所需市场冲击。

    线性穿透假设：策略 h 日损失 ≈ β × 市场 h 日冲击（β 用
    performance.beta 口径 cov/σ²_M）。所需市场冲击 S* = 阈值/β；
    在基准 h 日滚动累计收益分布上给出：
    - empirical_percentile：历史滚动窗口中累计收益 ≤ −S* 的占比
      （历史上多久出现一次这么深的市场冲击）；
    - sigma_multiple：S* / σ_roll（σ_roll = 滚动 h 日累计收益样本 std）。
    """
    if loss_threshold <= 0:
        raise ValueError("loss_threshold must be > 0（损失口径正数）")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    from quant_research_engine.risk.performance import beta as _beta

    r = _clean(strategy_returns)
    b = _clean(benchmark_returns)
    beta = _beta(r, b)
    if beta <= 0:
        raise ValueError(
            f"beta={beta:.4f} <= 0：市场冲击无法穿透为该策略损失，"
            "reverse stress 需改用假设性情景（书4 Ch8 ad hoc scenarios）"
        )
    required_shock = loss_threshold / beta

    rolling = (1.0 + b).rolling(horizon).apply(np.prod, raw=True) - 1.0
    rolling = rolling.dropna()
    if len(rolling) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} rolling {horizon}d windows, got {len(rolling)}")
    sigma_roll = float(rolling.std(ddof=1))
    percentile = float((rolling <= -required_shock).mean())
    return {
        "loss_threshold": loss_threshold,
        "horizon_days": horizon,
        "beta": beta,
        "required_market_shock": required_shock,
        "empirical_percentile": percentile,
        "sigma_multiple": (required_shock / sigma_roll) if sigma_roll > 0 else None,
        "n_rolling_windows": int(len(rolling)),
        "note": "线性穿透 策略损失≈β×市场冲击；S*=阈值/β 在基准 h 日滚动累计收益"
        "分布上取经验分位与 σ 倍数；情景放大 ×2/×3 是近似（书4 Ch8：压力期"
        "相关性上升，不能简单线性外推）",
    }
