"""大盘/板块风险风向标：组合法封装 + 分数归一化 + 预警判定 + 结果组装。

纯函数、零 DB（CR_2026-08-23_market_risk_barometer §2/§4）。

- 组合法（路线 A）：面板收益 + 权重 → 等权/市值加权组合日收益序列，
  复用 risk.volatility / risk.tail 出 EWMA σ 预测、VaR95/99、ES95/99
  （历史模拟 + EWMA 参数法），零新计算代码。
- 分数归一化：指标值对 252 日滚动历史（含当日）取分位数 ×100（0–100）；
  历史不足一个窗口 → 该日分数 None（warmup 降级，不伪造分数）。
- 预警判定：平均相关系数 20 日升幅 > 阈值 且 VaR 突破占比 > 阈值 → red；
  单超阈 → amber；否则 green。阈值集中 constants.py（初值 +0.10 / 3%，
  CR §2 注明需首批真实数据校准）并全部回显。
- 结果组装：全市场 + 板块统一 dict；板块分组映射由调用方传入
  （行业口径/动态簇口径均可），本模块不感知来源。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.risk import tail, volatility
from quant_research_engine.risk.constants import (
    BAROMETER_ALERT_BREACH_RATIO_MAX,
    BAROMETER_ALERT_CORR_JUMP,
    BAROMETER_ALERT_CORR_LOOKBACK,
    BAROMETER_SCORE_WINDOW,
    CONFIDENCE_LEVELS,
    EWMA_LAMBDA,
)

#: 风险总分的五个组成指标（四截面 + 组合法 ES99，各做滚动分位后等权合成；
#: 截面波动率取中位数为代表，90 分位作为辅助指标披露不进总分）
SCORE_COMPONENTS: tuple[str, ...] = (
    "median_sigma",
    "dispersion",
    "avg_pairwise_corr",
    "breach_ratio",
    "portfolio_es99",
)


def portfolio_return_series(
    returns: pd.DataFrame,
    weights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """面板收益 → 等权/市值加权组合日收益序列。

    等权 = 当日有效收益算术平均；市值加权 = 权重在当日有效收益股票上
    行内归一化后的加权和。weights 为 None 时仅输出等权列。
    当日无有效收益 → NaN。
    """
    if not isinstance(returns, pd.DataFrame) or returns.size == 0:
        raise ValueError("returns must be a non-empty DataFrame (dates × stocks)")
    frame = returns.astype(float)
    r = frame.to_numpy()
    valid = ~np.isnan(r)
    n = valid.sum(axis=1)
    r_filled = np.where(valid, r, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        ew = np.where(n > 0, r_filled.sum(axis=1) / np.maximum(n, 1), np.nan)
    out = pd.DataFrame({"r_equal_weight": ew, "n_stocks": n.astype(int)}, index=frame.index)
    if weights is not None:
        w = weights.astype(float).reindex_like(frame).to_numpy()
        w_valid = np.where(valid & ~np.isnan(w), w, 0.0)
        w_sum = w_valid.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            cw = np.where(w_sum > 0, (r_filled * w_valid).sum(axis=1) / np.where(w_sum > 0, w_sum, 1.0), np.nan)
        out["r_cap_weight"] = cw
    return out


def portfolio_risk_summary(
    portfolio_returns: pd.Series | np.ndarray | list[float],
    confidence_levels: tuple[float, ...] = CONFIDENCE_LEVELS,
    lam: float = EWMA_LAMBDA,
) -> dict[str, Any]:
    """组合收益序列 → EWMA σ 预测 + VaR/ES（历史模拟 + EWMA 参数法）。

    100% 复用 risk.volatility 与 risk.tail（路线 A 零新计算代码）。
    """
    r = pd.Series(portfolio_returns, dtype=float).dropna()
    ewma = volatility.latest_ewma_forecast(r, lam=lam)
    levels: dict[str, Any] = {}
    for conf in confidence_levels:
        key = f"{int(round(conf * 100))}pct"
        levels[key] = {
            "confidence": conf,
            "historical": tail.historical_var_es(r, confidence=conf),
            "ewma_parametric": tail.ewma_parametric_var_es(r, confidence=conf, lam=lam),
        }
    return {
        "n_obs": int(len(r)),
        "ewma_volatility_forecast": ewma["volatility_forecast"],
        "ewma_variance_forecast": ewma["variance_forecast"],
        "lambda": lam,
        "levels": levels,
        "note": "组合法（CR §2 路线 A）：复用 volatility.latest_ewma_forecast + tail.historical/ewma_parametric_var_es",
    }


def rolling_percentile_score(
    series: pd.Series | np.ndarray | list[float],
    window: int = BAROMETER_SCORE_WINDOW,
) -> pd.DataFrame:
    """指标对滚动窗口（含当日）的分位数分数（0–100）。

    score_t = 窗口内 ≤ x_t 的观测占比 × 100（≤ 口径，含当日自身）。
    可用历史不足 window → score 为 None 且 warmup=True（降级，不伪造）。
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    s = pd.Series(series, dtype=float)
    n = len(s)
    scores = np.full(n, np.nan)
    warmup = np.ones(n, dtype=bool)
    arr = s.to_numpy()
    for t in range(n):
        lo = max(0, t + 1 - window)
        hist = arr[lo : t + 1]
        hist = hist[~np.isnan(hist)]
        if t + 1 >= window and len(hist) >= 2 and not np.isnan(arr[t]):
            scores[t] = float(100.0 * np.sum(hist <= arr[t]) / len(hist))
            warmup[t] = False
    return pd.DataFrame({"score": scores, "warmup": warmup}, index=s.index)


def evaluate_alert(
    avg_corr_series: pd.Series | np.ndarray | list[float],
    breach_ratio_series: pd.Series | np.ndarray | list[float],
    corr_lookback: int = BAROMETER_ALERT_CORR_LOOKBACK,
    corr_jump: float = BAROMETER_ALERT_CORR_JUMP,
    breach_ratio_max: float = BAROMETER_ALERT_BREACH_RATIO_MAX,
) -> dict[str, Any]:
    """红灯预警判定（最新交易日口径）。

    相关系数 corr_lookback 日升幅 = 末值 − 末值前 corr_lookback 个非 NaN
    观测处取值；历史不足 → corr_jump_observed=None，该判据不触发（amber
    只由突破占比决定），如实披露。双超阈 → red，单超阈 → amber，
    否则 green。
    """
    if corr_lookback < 1:
        raise ValueError("corr_lookback must be >= 1")
    corr = pd.Series(avg_corr_series, dtype=float).dropna()
    breach = pd.Series(breach_ratio_series, dtype=float).dropna()
    if len(breach) < 1:
        raise ValueError("breach_ratio_series must have at least 1 non-NaN value")

    breach_latest = float(breach.iloc[-1])
    breach_exceed = bool(breach_latest > breach_ratio_max)

    corr_latest = float(corr.iloc[-1]) if len(corr) > 0 else None
    corr_change: float | None = None
    corr_exceed = False
    if len(corr) > corr_lookback:
        corr_change = float(corr.iloc[-1] - corr.iloc[-1 - corr_lookback])
        corr_exceed = bool(corr_change > corr_jump)

    if corr_exceed and breach_exceed:
        alert = "red"
    elif corr_exceed or breach_exceed:
        alert = "amber"
    else:
        alert = "green"
    return {
        "alert": alert,
        "corr_latest": corr_latest,
        "corr_change": corr_change,
        "corr_lookback": corr_lookback,
        "corr_jump_threshold": corr_jump,
        "corr_exceed": corr_exceed,
        "breach_ratio_latest": breach_latest,
        "breach_ratio_threshold": breach_ratio_max,
        "breach_exceed": breach_exceed,
        "note": "双超阈 red / 单超阈 amber / 否则 green；相关历史不足时 corr 判据不触发（如实披露，CR §2 阈值初值待校准）",
    }


def _latest_or_none(series: pd.Series) -> float | None:
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) > 0 else None


def build_barometer(
    returns: pd.DataFrame,
    weights: pd.DataFrame | None = None,
    groups: dict[str, list[str]] | None = None,
    score_window: int = BAROMETER_SCORE_WINDOW,
    lam: float = EWMA_LAMBDA,
    alert_kwargs: dict[str, Any] | None = None,
    cross_section_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """风向标结果组装：全市场 + 板块统一输出。

    每个 universe（market + 各 group）输出：
    - indicators：四截面指标 + 组合法 ES99 的最新值（与逐日序列）；
    - scores：五指标各自滚动分位（0–100）最新值，warmup 降级为 None；
      total_score = 非 warmup 指标的等权均值（任一 warmup → warmup=True；
      全部 warmup → None）；
    - alert：evaluate_alert 结果（相关系数升幅 + 突破占比双判据）。

    groups：{板块名: [股票代码...]}，来源（行业/动态簇）本模块不感知；
    组内股票在面板中不足 2 只 → 该组跳过并记入 skipped_groups。
    """
    from quant_research_engine.risk.cross_section import cross_sectional_summary

    alert_kwargs = dict(alert_kwargs or {})
    cs_kwargs = dict(cross_section_kwargs or {})

    def _universe(sub: pd.DataFrame, sub_w: pd.DataFrame | None) -> dict[str, Any]:
        cs = cross_sectional_summary(sub, weights=sub_w, lam=lam, **cs_kwargs)
        port = portfolio_return_series(sub, weights=sub_w)
        port_summary = {
            name: portfolio_risk_summary(port[col].dropna(), lam=lam)
            for name, col in (("equal_weight", "r_equal_weight"), ("cap_weight", "r_cap_weight"))
            if col in port.columns and int(port[col].notna().sum()) >= 2
        }
        corr_s = cs["sections"]["avg_pairwise_corr"]["avg_pairwise_corr_equal_weight"]
        breach_s = cs["sections"]["var_breach"]["breach_ratio"]
        es99_s = None
        if "equal_weight" in port_summary:
            # ES99 逐日序列（历史模拟滚动口径太重，此处用扩展窗口历史模拟）
            ew_series = port["r_equal_weight"].dropna()
            es99_s = ew_series.expanding(min_periods=2).apply(
                lambda x: tail.historical_var_es(x, confidence=0.99)["es"], raw=False
            )
        indicators = {
            "median_sigma": cs["sections"]["volatility_stats"]["median_sigma"],
            "sigma_q_high": cs["sections"]["volatility_stats"]["q_high_sigma"],
            "dispersion": cs["sections"]["dispersion"]["dispersion_equal_weight"],
            "avg_pairwise_corr": corr_s,
            "breach_ratio": breach_s,
            "n_stocks": cs["sections"]["dispersion"]["n_stocks"],
            "portfolio_es99": es99_s,
        }
        score_series = {
            k: rolling_percentile_score(indicators[k], window=score_window)
            for k in SCORE_COMPONENTS
            if indicators.get(k) is not None
        }
        latest_scores: dict[str, float | None] = {}
        any_warmup = False
        for k, sc in score_series.items():
            val = sc["score"].iloc[-1]
            warm = bool(sc["warmup"].iloc[-1])
            latest_scores[k] = None if warm else float(val)
            any_warmup = any_warmup or warm
        valid_scores = [v for v in latest_scores.values() if v is not None]
        total_score = float(np.mean(valid_scores)) if valid_scores else None
        alert = evaluate_alert(corr_s, breach_s, **alert_kwargs)
        return {
            "n_stocks_latest": int(cs["sections"]["dispersion"]["n_stocks"].iloc[-1]),
            "indicators_latest": {k: _latest_or_none(v) for k, v in indicators.items()},
            "indicator_series": indicators,
            "portfolio": port_summary,
            "portfolio_series": port,
            "scores_latest": latest_scores,
            "score_series": score_series,
            "total_score": total_score,
            "warmup": any_warmup,
            "alert": alert,
            "cross_section_params": cs["params"],
        }

    market = _universe(returns, weights)
    group_out: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    for name, codes in (groups or {}).items():
        cols = [c for c in codes if c in returns.columns]
        if len(cols) < 2:
            skipped[name] = f"fewer than 2 member stocks present in panel ({len(cols)})"
            continue
        sub_w = weights[cols] if weights is not None else None
        group_out[name] = _universe(returns[cols], sub_w)
    return {
        "market": market,
        "groups": group_out,
        "skipped_groups": skipped,
        "params": {
            "score_window": score_window,
            "lambda": lam,
            "score_components": list(SCORE_COMPONENTS),
            "alert": alert_kwargs or "defaults from risk.constants",
        },
        "note": "CR_2026-08-23_market_risk_barometer M1；分组映射由调用方传入（行业/簇口径不感知）；纯函数零 DB",
    }
