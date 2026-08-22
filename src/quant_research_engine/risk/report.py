"""统一风险报告骨架（机读 JSON；markdown 渲染留 R3）。

``build_risk_report(returns, benchmark=None, config=None) -> dict``：

- returns：策略逐日 simple 收益序列（回测产物）。
- benchmark：可选基准逐日收益；None 时基准相关节为 null 而不报错。
- config：可选 dict 覆盖常量（confidence_levels/lam/risk_free_rate/
  annualization_factor/regime_quantiles），以及 R2 节开关：
  - ``var_backtest``（默认 True）：VaR 回测节；VaR 序列默认用 R1 EWMA
    预测（σ_t = ewma_forecast_series 开根，μ=0 RiskMetrics 口径，
    VaR_t = z_X·σ_t，note 披露）；``var_series`` 可显式传入覆盖默认。
  - ``stress``（默认 False）：历史情景回放节；需 DatetimeIndex returns；
    ``scenarios`` 可自定义情景库；``reverse_stress_threshold``（损失口径
    正数）+ benchmark 时附 reverse stress。
  - ``bootstrap``（默认 False）：CBB 置信区间节；``bootstrap_reps`` /
    ``bootstrap_seed`` / ``bootstrap_ci_level`` / ``block_size`` 可配。
  其余键原样忽略。

结构键：meta（参数回显）、distribution、tail（三口径 × 置信水平）、
volatility（ewma/garch/regime）、dependence（需 benchmark）、performance、
var_backtest、stress（可选）、bootstrap（可选）。
数据不足（如 GARCH < 50 obs）的节返回 ``{"error": ...}`` 而非抛异常。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.risk import (
    backtest_var,
    dependence,
    inference,
    performance,
    stress,
    tail,
    volatility,
)
from quant_research_engine.risk.constants import (
    ANNUALIZATION_FACTOR,
    BOOTSTRAP_CI_LEVEL,
    BOOTSTRAP_REPLICATIONS,
    BOOTSTRAP_SEED,
    CONFIDENCE_LEVELS,
    DEFAULT_RISK_FREE_RATE,
    EWMA_LAMBDA,
    REGIME_QUANTILES,
    z_value,
)

_REPORT_VERSION = "R2"


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
            "sections": {
                "var_backtest": bool(cfg.get("var_backtest", True)),
                "stress": bool(cfg.get("stress", False)),
                "bootstrap": bool(cfg.get("bootstrap", False)),
            },
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
        "var_backtest": _build_var_backtest_section(r, cfg, confidence_levels, lam),
    }

    if cfg.get("stress", False):
        report["stress"] = _build_stress_section(
            r, benchmark, cfg, confidence_levels, lam
        )
    if cfg.get("bootstrap", False):
        report["bootstrap"] = _build_bootstrap_section(r, cfg, rf, ann)
    return report


def _default_var_series(r: pd.Series, confidence: float, lam: float) -> pd.Series:
    """默认 VaR 序列：VaR_t = z_X·σ_t，σ_t = EWMA 次日预测（shift(1) PIT），μ=0。"""
    sigma = np.sqrt(volatility.ewma_forecast_series(r, lam=lam))
    return z_value(confidence) * sigma


def _build_var_backtest_section(
    r: pd.Series,
    cfg: dict[str, Any],
    confidence_levels: tuple[float, ...],
    lam: float,
) -> dict[str, Any]:
    if not cfg.get("var_backtest", True):
        return {"enabled": False}
    section: dict[str, Any] = {"enabled": True, "levels": {}}
    explicit_var = cfg.get("var_series")
    for level in confidence_levels:
        key = f"{int(round(level * 100))}pct"
        if explicit_var is not None:
            var_series: pd.Series | dict[str, Any] = pd.Series(explicit_var, dtype=float)
            var_source = "config.var_series（调用方显式提供）"
        else:
            var_series = _safe(_default_var_series, r, level, lam)
            var_source = (
                "默认 EWMA 参数 VaR：VaR_t = z_X·σ_t，σ_t = sqrt(ewma_forecast_series)"
                "（raw.shift(1) 防前视），μ=0 RiskMetrics 口径"
            )
        if "error" in var_series:
            section["levels"][key] = {**var_series, "var_source": var_source}
            continue
        entry = _safe(backtest_var.backtest_var_summary, r, var_series, level)
        entry["var_source"] = var_source
        section["levels"][key] = entry
    section["false_positive_warning"] = {
        "alpha": 0.05,
        "examples": {
            "n_tests_10": backtest_var.false_positive_probability(0.05, 10),
            "n_tests_100": backtest_var.false_positive_probability(0.05, 100),
        },
        "note": "n 个独立检验名义 5% 下至少一个假阳性概率 1−0.95ⁿ（书2 Ch6）："
        "多策略/多参数同批回测时 VaR 回测拒绝需按多重检验口径解读",
    }
    return section


def _build_stress_section(
    r: pd.Series,
    benchmark: pd.Series | np.ndarray | list[float] | None,
    cfg: dict[str, Any],
    confidence_levels: tuple[float, ...],
    lam: float,
) -> dict[str, Any]:
    if not isinstance(r.index, pd.DatetimeIndex):
        return {"error": "stress 节需要 DatetimeIndex returns（情景窗口按日期切片）"}
    level = max(confidence_levels)
    current = _safe(tail.ewma_parametric_var_es, r, level, lam)
    var = current.get("var") if "error" not in current else None
    es = current.get("es") if "error" not in current else None
    section: dict[str, Any] = {
        "scenarios": _safe(
            stress.replay_historical_scenarios,
            r,
            benchmark,
            var,
            es,
            cfg.get("scenarios"),
        ),
        "var_es_reference": {
            "confidence": level,
            "method": "ewma_parametric",
            "var": var,
            "es": es,
            "note": "Peak/VaR 与 Peak/ES 的参照 VaR/ES（当前 1 日 EWMA 参数法，损失口径）",
        },
    }
    threshold = cfg.get("reverse_stress_threshold")
    if threshold is not None and benchmark is not None:
        section["reverse_stress"] = _safe(
            stress.reverse_stress,
            r,
            benchmark,
            float(threshold),
            int(cfg.get("reverse_stress_horizon", 21)),
        )
    elif threshold is not None:
        section["reverse_stress"] = {"error": "reverse stress 需要 benchmark（β 穿透与滚动分布）"}
    return section


def _build_bootstrap_section(
    r: pd.Series,
    cfg: dict[str, Any],
    rf: float,
    ann: int,
) -> dict[str, Any]:
    return _safe(
        inference.bootstrap_summary,
        r,
        inference.METRIC_NAMES,
        int(cfg.get("bootstrap_reps", BOOTSTRAP_REPLICATIONS)),
        cfg.get("block_size"),
        float(cfg.get("bootstrap_ci_level", BOOTSTRAP_CI_LEVEL)),
        cfg.get("bootstrap_seed", BOOTSTRAP_SEED),
        rf,
        ann,
    )
