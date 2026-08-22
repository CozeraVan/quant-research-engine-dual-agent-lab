"""统一风险报告骨架（R1 机读 JSON；markdown 渲染留 R3）。

``build_risk_report(returns, benchmark=None, config=None) -> dict``：

- returns：策略逐日 simple 收益序列（回测产物）。
- benchmark：可选基准逐日收益；None 时基准相关节为 null 而不报错。
- config：可选 dict 覆盖常量（confidence_levels/lam/risk_free_rate/
  annualization_factor/regime_quantiles），其余键原样忽略。

结构键：meta（参数回显）、distribution、tail（三口径 × 置信水平）、
volatility（ewma/garch/regime）、dependence（需 benchmark）、performance。
数据不足（如 GARCH < 50 obs）的节返回 ``{"error": ...}`` 而非抛异常。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.risk import dependence, performance, tail, volatility
from quant_research_engine.risk.constants import (
    ANNUALIZATION_FACTOR,
    CONFIDENCE_LEVELS,
    DEFAULT_RISK_FREE_RATE,
    EWMA_LAMBDA,
    REGIME_QUANTILES,
)

_REPORT_VERSION = "R1"


def _safe(fn, *args, **kwargs) -> dict[str, Any]:
    """数据不足等可预期失败降级为 error 节，不拖垮整份报告。"""
    try:
        return fn(*args, **kwargs)
    except (ValueError, np.linalg.LinAlgError) as exc:
        return {"error": str(exc)}


def build_risk_report(
    returns: pd.Series | np.ndarray | list[float],
    benchmark: pd.Series | np.ndarray | list[float] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建机读风险报告 dict（可直接 json.dumps）。"""
    cfg = dict(config or {})
    confidence_levels = tuple(cfg.get("confidence_levels", CONFIDENCE_LEVELS))
    lam = float(cfg.get("lam", EWMA_LAMBDA))
    rf = float(cfg.get("risk_free_rate", DEFAULT_RISK_FREE_RATE))
    ann = int(cfg.get("annualization_factor", ANNUALIZATION_FACTOR))
    regime_q = tuple(cfg.get("regime_quantiles", REGIME_QUANTILES))

    r = pd.Series(returns, dtype=float).dropna()

    tail_section: dict[str, Any] = {}
    for level in confidence_levels:
        key = f"{int(round(level * 100))}pct"
        tail_section[key] = {
            "parametric_normal": _safe(tail.parametric_normal_var_es, r, level),
            "historical_simulation": _safe(tail.historical_var_es, r, level),
            "ewma_parametric": _safe(tail.ewma_parametric_var_es, r, level, lam),
        }

    ewma_latest = _safe(volatility.latest_ewma_forecast, r, lam)
    garch = _safe(volatility.fit_garch11, r)
    vol_series = _safe(volatility.ewma_volatility_series, r, lam)
    if "error" in vol_series:
        regime_section: dict[str, Any] = vol_series
    else:
        regime = volatility.volatility_regime(vol_series, regime_q)
        regime_section = {
            "quantiles": list(regime_q),
            "counts": {k: int(v) for k, v in regime.value_counts().items()},
            "latest": str(regime.iloc[-1]),
            "note": "分位规则写死：σ<q1→low，q1≤σ<q2→mid，≥q2→high（按自身样本分位）",
        }

    if benchmark is None:
        dependence_section: dict[str, Any] = {
            "spearman_vs_benchmark": None,
            "kendall_vs_benchmark": None,
        }
        perf_benchmark = None
    else:
        b = pd.Series(benchmark, dtype=float)
        dependence_section = {
            "spearman_vs_benchmark": _safe(dependence.spearman_corr, r, b),
            "kendall_vs_benchmark": _safe(dependence.kendall_corr, r, b),
        }
        perf_benchmark = b

    report = {
        "meta": {
            "report_version": _REPORT_VERSION,
            "n_obs": int(len(r)),
            "confidence_levels": list(confidence_levels),
            "ewma_lambda": lam,
            "risk_free_rate_annual": rf,
            "annualization_factor": ann,
            "regime_quantiles": list(regime_q),
            "loss_sign_convention": "loss = -return（损失取正号，书4 Ch1）",
            "has_benchmark": benchmark is not None,
        },
        "distribution": _safe(tail.distribution_summary, r),
        "tail": tail_section,
        "volatility": {
            "ewma_latest": ewma_latest,
            "garch11": garch,
            "regime": regime_section,
        },
        "dependence": dependence_section,
        "performance": _safe(performance.performance_summary, r, perf_benchmark, rf, ann),
    }
    return report
