"""统一风险报告（机读 JSON + R3 markdown 渲染）。

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


# ---------------------------------------------------------------------------
# R3：markdown 渲染（人读；汉化，比率两位小数，p 值四位小数）
# ---------------------------------------------------------------------------

_METHOD_LABELS = {
    "parametric_normal": "参数正态",
    "historical_simulation": "历史模拟",
    "ewma_parametric": "EWMA 参数",
}


def _f2(value: Any) -> str:
    """两位小数；None/非数值原样或 —。"""
    if value is None or isinstance(value, bool):
        return "—" if value is None else str(value)
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    """小数 → 百分比两位（0.0123 → 1.23%）。"""
    if value is None or isinstance(value, bool):
        return "—"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _p4(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _err(section: Any) -> str | None:
    """error 节降级文本；非 error 返回 None。"""
    if isinstance(section, dict) and "error" in section:
        return f"数据不足或不可用：{section['error']}"
    return None


def render_risk_markdown(report: dict[str, Any]) -> str:
    """把 build_risk_report 的机读 dict 渲染为汉化 markdown（「## 风险分析」节）。

    分区：分布与尾部 / VaR 回测 / 波动率 / 压力测试（有键才渲染）/ 绩效
    （+ bootstrap CI，有键才渲染）。error 节如实降级为「数据不足」一行。
    """
    meta = report.get("meta", {})
    lines: list[str] = [
        "## 风险分析",
        "",
        f"> QRE risk 包自动生成（报告版本 {meta.get('report_version', '?')}；"
        f"样本 n={meta.get('n_obs', '?')}；损失取正号，置信水平 "
        + "/".join(f"{float(x) * 100:.0f}%" for x in meta.get("confidence_levels", []))
        + "；仅风险度量，非投资建议）",
        "",
    ]

    # --- 分布与尾部 ---
    lines.append("### 分布与尾部")
    lines.append("")
    dist = report.get("distribution", {})
    err = _err(dist)
    if err:
        lines.append(f"- {err}")
    else:
        lines.append(
            f"- 日收益：均值 {_pct(dist.get('mean'))}，标准差 {_pct(dist.get('std'))}，"
            f"最小 {_pct(dist.get('min'))}，最大 {_pct(dist.get('max'))}"
        )
        lines.append(
            f"- 偏度 {_f2(dist.get('skew_sample'))}，超额峰度 "
            f"{_f2(dist.get('excess_kurtosis_sample'))}（正态=0）"
        )
        reject = dist.get("reject_normal_5pct")
        verdict = "拒绝正态（5%）" if reject else "不拒绝正态（5%）"
        lines.append(
            f"- Jarque-Bera：统计量 {_f2(dist.get('jb_statistic'))}，"
            f"p={_p4(dist.get('jb_p_value'))} → {verdict}"
        )
    tail_section = report.get("tail", {})
    if tail_section:
        lines.append("")
        lines.append("| 置信水平 | 口径 | VaR（日损失） | ES（日损失） |")
        lines.append("|---|---|---|---|")
        for level_key, methods in tail_section.items():
            level_label = level_key.replace("pct", "%")
            for method_key, entry in methods.items():
                label = _METHOD_LABELS.get(method_key, method_key)
                if isinstance(entry, dict) and "error" in entry:
                    lines.append(f"| {level_label} | {label} | 数据不足 | 数据不足 |")
                else:
                    lines.append(
                        f"| {level_label} | {label} | {_pct(entry.get('var'))} "
                        f"| {_pct(entry.get('es'))} |"
                    )
    lines.append("")

    # --- VaR 回测 ---
    var_bt = report.get("var_backtest", {})
    if var_bt.get("enabled"):
        lines.append("### VaR 回测（HIT / 覆盖率 LR / 独立性 LR）")
        lines.append("")
        lines.append("| 置信水平 | 违约数/期望 | 违约率 | 覆盖率 LR p | 独立性 LR p | 结论 |")
        lines.append("|---|---|---|---|---|---|")
        for level_key, entry in var_bt.get("levels", {}).items():
            level_label = level_key.replace("pct", "%")
            if not isinstance(entry, dict) or "error" in entry:
                msg = entry.get("error", "?") if isinstance(entry, dict) else "?"
                lines.append(f"| {level_label} | 数据不足：{msg} | — | — | — | — |")
                continue
            lines.append(
                f"| {level_label} | {entry.get('violations')}/"
                f"{_f2(entry.get('expected_violations'))} | "
                f"{_pct(entry.get('violation_rate'))} | "
                f"{_p4((entry.get('coverage') or {}).get('p_value'))} | "
                f"{_p4((entry.get('independence') or {}).get('p_value'))} | "
                f"{entry.get('conclusion', '—')} |"
            )
        fp = var_bt.get("false_positive_warning", {})
        if fp:
            lines.append("")
            lines.append(f"- 多重检验警示：{fp.get('note', '')}")
        lines.append("")

    # --- 波动率 ---
    vol = report.get("volatility", {})
    lines.append("### 波动率")
    lines.append("")
    ewma = vol.get("ewma_latest", {})
    err = _err(ewma)
    if err:
        lines.append(f"- EWMA：{err}")
    else:
        ann = meta.get("annualization_factor", 252)
        daily_vol = ewma.get("volatility_forecast")
        ann_vol = (daily_vol * ann**0.5) if isinstance(daily_vol, (int, float)) else None
        lines.append(
            f"- EWMA（λ={ewma.get('lambda')}）次日波动预测：日 {_pct(daily_vol)}"
            f"（年化 {_pct(ann_vol)}）"
        )
    garch = vol.get("garch11", {})
    err = _err(garch)
    if err:
        lines.append(f"- GARCH(1,1)：{err}")
    else:
        lines.append(
            f"- GARCH(1,1)：α+β={_f2(garch.get('persistence'))}"
            f"（{'平稳' if garch.get('stationary') else '非平稳'}），"
            f"长期波动 {_pct(garch.get('long_run_volatility'))}（日），"
            f"最新条件波动 {_pct(garch.get('latest_conditional_volatility'))}（日），"
            f"半衰期 {_f2(garch.get('half_life_days'))} 天"
        )
    regime = vol.get("regime", {})
    err = _err(regime)
    if err:
        lines.append(f"- 波动率 regime：{err}")
    elif regime:
        lines.append(
            f"- 当前波动率 regime：**{regime.get('latest', '—')}**"
            f"（按自身样本分位 {[_f2(q) for q in regime.get('quantiles', [])]} 分 low/mid/high）"
        )
    lines.append("")

    # --- 压力测试 ---
    stress_section = report.get("stress")
    if isinstance(stress_section, dict):
        lines.append("### 压力测试（历史情景回放）")
        lines.append("")
        err = _err(stress_section)
        if err:
            lines.append(f"- {err}")
        else:
            scenarios = stress_section.get("scenarios", {})
            lines.append("| 情景 | 窗口 | 天数 | 累计损失 | 峰谷回撤 | Peak/VaR |")
            lines.append("|---|---|---|---|---|---|")
            for name, entry in scenarios.items():
                if not isinstance(entry, dict):
                    continue
                if "error" in entry:
                    lines.append(f"| {name} | — | — | 样本不覆盖该窗口 | — | — |")
                    continue
                window = entry.get("window", {})
                lines.append(
                    f"| {name} | {window.get('start', '?')}~{window.get('end', '?')} "
                    f"| {entry.get('n_days')} | {_pct(entry.get('strategy_cumulative_loss'))} "
                    f"| {_pct(entry.get('strategy_peak_trough_drawdown'))} "
                    f"| {_f2(entry.get('peak_to_var'))} |"
                )
            ref = stress_section.get("var_es_reference", {})
            if ref:
                lines.append("")
                lines.append(
                    f"- Peak/VaR 参照：当前 1 日 {float(ref.get('confidence', 0)) * 100:.0f}% "
                    f"EWMA 参数 VaR={_pct(ref.get('var'))}、ES={_pct(ref.get('es'))}"
                )
            reverse = stress_section.get("reverse_stress")
            if isinstance(reverse, dict):
                if "error" in reverse:
                    lines.append(f"- Reverse stress：{reverse['error']}")
                else:
                    lines.append(
                        f"- Reverse stress：亏损阈值 {_pct(reverse.get('loss_threshold'))} "
                        f"需市场冲击 {_pct(reverse.get('required_market_shock'))}"
                        f"（β={_f2(reverse.get('beta'))}），历史滚动分位 "
                        f"{_pct(reverse.get('empirical_percentile'))}，"
                        f"σ 倍数 {_f2(reverse.get('sigma_multiple'))}"
                    )
        lines.append("")

    # --- 绩效 ---
    perf = report.get("performance", {})
    lines.append("### 绩效风险指标")
    lines.append("")
    err = _err(perf)
    if err:
        lines.append(f"- {err}")
    else:
        sharpe = (perf.get("sharpe") or {}).get("sharpe")
        sortino = (perf.get("sortino") or {}).get("sortino")
        lines.append(f"- Sharpe {_f2(sharpe)}，Sortino {_f2(sortino)}（年化，rf={_pct(perf.get('risk_free_rate_annual'))}）")
        if perf.get("beta") is not None:
            treynor = (perf.get("treynor") or {}).get("treynor")
            ir = (perf.get("information_ratio") or {}).get("information_ratio")
            alpha = (perf.get("jensens_alpha") or {}).get("alpha_annual")
            lines.append(
                f"- β {_f2(perf.get('beta'))}，Treynor {_f2(treynor)}，"
                f"IR {_f2(ir)}，Jensen's α（年化）{_pct(alpha)}"
            )
        else:
            lines.append("- 无基准收益序列：β/Treynor/IR/Jensen's α 未计算")
    lines.append("")

    # --- bootstrap（按需任务才开启） ---
    boot = report.get("bootstrap")
    if isinstance(boot, dict):
        lines.append("### Bootstrap 置信区间（CBB）")
        lines.append("")
        err = _err(boot)
        if err:
            lines.append(f"- {err}")
        else:
            lines.append("| 指标 | 点估计 | CI 下界 | CI 上界 | MC 标准误 | iid 对照低估 |")
            lines.append("|---|---|---|---|---|---|")
            for name, entry in boot.items():
                if not isinstance(entry, dict) or "error" in entry:
                    continue
                cbb = entry.get("cbb", {})
                if not isinstance(cbb, dict) or "sample_statistic" not in cbb:
                    continue
                lines.append(
                    f"| {name} | {_f2(cbb.get('sample_statistic'))} "
                    f"| {_f2(cbb.get('ci_lower'))} | {_f2(cbb.get('ci_upper'))} "
                    f"| {_f2(cbb.get('mc_standard_error'))} "
                    f"| {'是' if entry.get('iid_underestimates') else '否'} |"
                )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
