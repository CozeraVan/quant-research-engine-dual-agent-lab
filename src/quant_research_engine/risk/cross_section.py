"""截面聚合指标（自下而上，CR_2026-08-23_market_risk_barometer §2 路线 B）。

纯函数、零 DB：输入为「交易日 × 个股」收益/波动率面板（pandas DataFrame，
行=交易日升序、列=股票代码）与可选权重面板（市值权重，逐行归一化）。

- EWMA 方差面板：与 volatility.ewma_variance_series 口径逐键一致
  （σ²_1 = r²_1、σ²_n = λσ²_{n−1} + (1−λ)r²_n，λ=0.94）；NaN 观测跳过、
  方差顺延，等价于逐列 dropna 后递推（向量化实现，仅沿时间轴循环）。
- 截面波动率统计：逐日 σ 中位数与高分位（默认 90 分位，常量回显）。
- 截面离散度：当日收益的等权标准差与市值加权标准差
  （权重行内归一化，Σw·(r−μ_w)² 口径，披露为集中度未校正的常用近似）。
- 平均两两相关系数：滚动窗口（默认 60 交易日）内个股收益两两相关的
  均值。等权版 = 相关矩阵严格上三角均值；市值加权版 = 以 w_i·w_j 为
  偶权的加权均值（常规近似，非严格的加权相关系数，docstring 披露）。
  窗口内个股按列均值/标准差标准化，非 NaN 观测不足整个窗口的个股
  当日剔除（完整窗口口径，避免成对观测数不一致的伪相关）。
- VaR 突破占比：当日实际收益跌破各自 VaR（损失正号口径 r < −VaR）
  的计数与占比；个股 VaR 由调用方用 EWMA 法给出（本模块不规定口径）。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.risk.constants import (
    BAROMETER_BREACH_CONFIDENCE,
    BAROMETER_CORR_WINDOW,
    CROSS_SECTION_SIGMA_QUANTILE,
    EWMA_LAMBDA,
)


def _validate_panel(panel: pd.DataFrame, name: str) -> pd.DataFrame:
    if not isinstance(panel, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame (dates × stocks)")
    if panel.shape[0] < 1 or panel.shape[1] < 1:
        raise ValueError(f"{name} must be non-empty, got shape {panel.shape}")
    return panel.astype(float)


def ewma_variance_panel(
    returns: pd.DataFrame,
    lam: float = EWMA_LAMBDA,
) -> pd.DataFrame:
    """逐列 EWMA 条件方差面板（raw 口径，与 volatility 单列口径一致）。

    递推：σ²_1 = r²_1（各列首个非 NaN 观测初始化）；NaN 观测跳过、
    方差顺延（等价于逐列 dropna 后递推再按原索引放回）。
    point-in-time 对齐仍需 shift(1)（同 volatility 模块约定）。
    """
    if not 0.0 < lam < 1.0:
        raise ValueError("lam must be in (0, 1)")
    frame = _validate_panel(returns, "returns")
    arr = frame.to_numpy()
    n_dates, _ = arr.shape
    var = np.full_like(arr, np.nan)
    prev = np.full(arr.shape[1], np.nan)
    for t in range(n_dates):
        row = arr[t]
        valid = ~np.isnan(row)
        updated = np.where(valid & np.isnan(prev), row**2, lam * prev + (1.0 - lam) * row**2)
        prev = np.where(valid, updated, prev)
        var[t] = prev
    return pd.DataFrame(var, index=frame.index, columns=frame.columns)


def cross_sectional_volatility_stats(
    sigma_panel: pd.DataFrame,
    quantile: float = CROSS_SECTION_SIGMA_QUANTILE,
) -> pd.DataFrame:
    """逐日截面波动率统计：中位数、高分位、覆盖股票数。

    输入为个股 EWMA σ 面板（方差面板请先开根）；全 NaN 日期结果为 NaN、
    n_stocks=0。
    """
    if not 0.0 < quantile < 1.0:
        raise ValueError("quantile must be in (0, 1)")
    frame = _validate_panel(sigma_panel, "sigma_panel")
    arr = frame.to_numpy()
    with np.errstate(all="ignore"):
        median = np.nanmedian(arr, axis=1)
        q_high = np.nanquantile(arr, quantile, axis=1)
    n = np.sum(~np.isnan(arr), axis=1)
    out = pd.DataFrame(
        {
            "median_sigma": median,
            "q_high_sigma": q_high,
            "n_stocks": n.astype(int),
        },
        index=frame.index,
    )
    out.attrs["quantile"] = quantile
    return out


def cross_sectional_dispersion(
    returns: pd.DataFrame,
    weights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """逐日截面离散度：当日收益的等权/市值加权标准差。

    加权口径：权重在当日有效收益股票上行内归一化，μ_w = Σw·r，
    σ_w² = Σw·(r−μ_w)²（未做 1−Σw² 集中度校正的常用近似，披露）。
    weights 为 None 时仅输出等权列。
    """
    frame = _validate_panel(returns, "returns")
    r = frame.to_numpy()
    valid = ~np.isnan(r)
    n = valid.sum(axis=1)

    def _row_std(row: np.ndarray, mask: np.ndarray, w: np.ndarray | None) -> float:
        vals = row[mask]
        if len(vals) < 2:
            return np.nan
        if w is None:
            return float(np.std(vals, ddof=1))
        wv = w[mask]
        total = wv.sum()
        if not np.isfinite(total) or total <= 0:
            return np.nan
        wn = wv / total
        mu = float(np.sum(wn * vals))
        return float(np.sqrt(np.sum(wn * (vals - mu) ** 2)))

    ew = np.array([_row_std(r[t], valid[t], None) for t in range(len(frame))])
    out = pd.DataFrame({"dispersion_equal_weight": ew, "n_stocks": n.astype(int)}, index=frame.index)
    if weights is not None:
        w_frame = _validate_panel(weights, "weights").reindex_like(frame)
        w = w_frame.to_numpy()
        cw = np.array([_row_std(r[t], valid[t], w[t]) for t in range(len(frame))])
        out["dispersion_cap_weight"] = cw
    return out


def average_pairwise_correlation(
    returns: pd.DataFrame,
    window: int = BAROMETER_CORR_WINDOW,
    weights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """滚动窗口平均两两相关系数（等权 + 可选市值加权）。

    每个交易日取前 window 行（含当日，不足 window 行则当日为 NaN）；
    窗口内非 NaN 观测不足 window 的个股当日剔除（完整窗口口径）。
    等权 = 相关矩阵严格上三角均值。市值加权 = 以 w_i·w_j（当日权重
    行内归一化）为偶权的上三角加权均值——常规近似：它是「按市值对
    相关性贡献加权」的聚合，并非严格意义的加权相关系数，如实披露。
    当日有效个股 <2 → NaN。
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    frame = _validate_panel(returns, "returns")
    r = frame.to_numpy()
    n_dates = frame.shape[0]
    w_arr = None
    if weights is not None:
        w_arr = _validate_panel(weights, "weights").reindex_like(frame).to_numpy()

    ew = np.full(n_dates, np.nan)
    cw = np.full(n_dates, np.nan)
    n_used = np.zeros(n_dates, dtype=int)
    for t in range(n_dates):
        if t + 1 < window:
            continue
        block = r[t + 1 - window : t + 1]
        complete = ~np.isnan(block).any(axis=0)
        cols = np.where(complete)[0]
        n_used[t] = len(cols)
        if len(cols) < 2:
            continue
        sub = block[:, cols]
        z = (sub - sub.mean(axis=0)) / sub.std(axis=0, ddof=1)
        corr = (z.T @ z) / (window - 1)
        # 数值噪声下对角线可能略偏离 1，只取严格上三角
        iu = np.triu_indices(len(cols), k=1)
        pairs = corr[iu]
        ew[t] = float(pairs.mean())
        if w_arr is not None:
            w_row = w_arr[t, cols]
            total = np.nansum(w_row)
            if np.isfinite(total) and total > 0:
                wn = w_row / total
                pw = np.outer(wn, wn)[iu]
                pw_sum = pw.sum()
                if pw_sum > 0:
                    cw[t] = float(np.sum(pw * pairs) / pw_sum)
    out = pd.DataFrame(
        {
            "avg_pairwise_corr_equal_weight": ew,
            "n_stocks": n_used,
        },
        index=frame.index,
    )
    if w_arr is not None:
        out["avg_pairwise_corr_cap_weight"] = cw
    out.attrs["window"] = window
    return out


def var_breach_ratio_series(
    returns: pd.DataFrame,
    var_panel: pd.DataFrame,
    confidence: float = BAROMETER_BREACH_CONFIDENCE,
) -> pd.DataFrame:
    """逐日 VaR 突破计数/占比：r < −VaR（损失正号口径，同 backtest_var HIT）。

    returns 为当日实际收益面板，var_panel 为同日各股 1 日 VaR（损失口径，
    正数，point-in-time 对齐由调用方保证，建议 EWMA 预测 shift(1)）。
    任一侧 NaN 的个股当日剔除。
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    r = _validate_panel(returns, "returns")
    v = _validate_panel(var_panel, "var_panel").reindex_like(r)
    r_arr, v_arr = r.to_numpy(), v.to_numpy()
    valid = ~np.isnan(r_arr) & ~np.isnan(v_arr)
    breaches = (valid & (r_arr < -v_arr)).sum(axis=1)
    n = valid.sum(axis=1)
    ratio = np.where(n > 0, breaches / np.maximum(n, 1), np.nan)
    out = pd.DataFrame(
        {
            "n_stocks": n.astype(int),
            "breaches": breaches.astype(int),
            "breach_ratio": ratio,
        },
        index=r.index,
    )
    out.attrs["confidence"] = confidence
    return out


def cross_sectional_summary(
    returns: pd.DataFrame,
    weights: pd.DataFrame | None = None,
    lam: float = EWMA_LAMBDA,
    corr_window: int = BAROMETER_CORR_WINDOW,
    sigma_quantile: float = CROSS_SECTION_SIGMA_QUANTILE,
    breach_confidence: float = BAROMETER_BREACH_CONFIDENCE,
) -> dict[str, Any]:
    """截面指标一把梭：EWMA σ 面板 → 波动率统计/离散度/平均相关/VaR 突破。

    VaR 突破用 EWMA 参数法（μ=0、z·σ_forecast、σ forecast = raw.shift(1)
    防前视）；返回逐日指标 DataFrame（sections）+ 参数回显。
    """
    from quant_research_engine.risk.constants import z_value

    var_panel = ewma_variance_panel(returns, lam=lam)
    sigma_panel = np.sqrt(var_panel)
    sigma_forecast = sigma_panel.shift(1)
    var99 = sigma_forecast * z_value(breach_confidence)
    sections = {
        "volatility_stats": cross_sectional_volatility_stats(sigma_panel, quantile=sigma_quantile),
        "dispersion": cross_sectional_dispersion(returns, weights=weights),
        "avg_pairwise_corr": average_pairwise_correlation(returns, window=corr_window, weights=weights),
        "var_breach": var_breach_ratio_series(returns, var99, confidence=breach_confidence),
    }
    return {
        "sections": sections,
        "params": {
            "lambda": lam,
            "corr_window": corr_window,
            "sigma_quantile": sigma_quantile,
            "breach_confidence": breach_confidence,
            "breach_var_method": "ewma_parametric mu=0, sigma=EWMA raw.shift(1) (point-in-time)",
        },
        "note": "CR_2026-08-23_market_risk_barometer §2 路线 B；EWMA 口径同 volatility.ewma_variance_series",
    }
