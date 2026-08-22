"""Bootstrap 推断（书2 Ch13）：CBB / iid 重抽样给回测指标算置信区间。

- Circular Block Bootstrap：arch.bootstrap.CircularBlockBootstrap，块长
  默认 q = ceil(√n)（教材经验法则 q≈√n）；块内连续、块间有放回、越界
  回绕，保留波动聚类等序列依赖。
- iid bootstrap 对照：教材明确 iid 破坏时间依赖、在波动聚类下低估不确定
  性（式 13.11 后讨论：0.1% VaR，CBB 53.5% vs iid 44.1%）；A 股波动聚类
  极强，摘要要求「禁用 iid bootstrap」——iid 在此仅作教学对照并标注。
- 指标：年化收益（日均 ×252）、夏普（与 performance.sharpe_ratio 同口径
  的日频均值/标准差 ×√252，rf 可配）、最大回撤（净值峰谷，损失口径）。
- MC 标准误：σ̂_g/√b（式 13.3），随每次运行输出；置信区间取 bootstrap
  分布的 (α/2, 1−α/2) 分位（percentile 法）。
- 固定随机种子、记录 b 与标准误作为回测报告要件（教材：可复现性/监管合规）。
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from quant_research_engine.risk.constants import (
    ANNUALIZATION_FACTOR,
    BOOTSTRAP_CI_LEVEL,
    BOOTSTRAP_REPLICATIONS,
    BOOTSTRAP_SEED,
    DEFAULT_RISK_FREE_RATE,
    default_block_size,
)

_MIN_OBS = 4


def _annualized_return(r: np.ndarray, ann: int, rf: float) -> float:
    return float(r.mean() * ann)


def _sharpe(r: np.ndarray, ann: int, rf: float) -> float:
    std = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    if std <= 0:
        return 0.0
    return float(((r - rf / ann).mean() / std) * ann**0.5)


def _max_drawdown(r: np.ndarray, ann: int, rf: float) -> float:
    nav = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(nav)
    return float(np.max(1.0 - nav / peak))


_METRICS: dict[str, Callable[[np.ndarray, int, float], float]] = {
    "annualized_return": _annualized_return,
    "sharpe": _sharpe,
    "max_drawdown": _max_drawdown,
}

METRIC_NAMES: tuple[str, ...] = tuple(_METRICS)


def _metric_fn(name: str) -> Callable[[np.ndarray, int, float], float]:
    if name not in _METRICS:
        raise ValueError(f"unknown metric {name!r}; choose from {sorted(_METRICS)}")
    return _METRICS[name]


def bootstrap_metric_ci(
    returns: pd.Series | np.ndarray | list[float],
    metric: str = "sharpe",
    method: str = "cbb",
    n_bootstrap: int = BOOTSTRAP_REPLICATIONS,
    block_size: int | None = None,
    ci_level: float = BOOTSTRAP_CI_LEVEL,
    seed: int | None = BOOTSTRAP_SEED,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """单指标 bootstrap 置信区间（书2 Ch13）。

    - method="cbb"：CircularBlockBootstrap（arch），块长默认 ceil(√n)。
    - method="iid"：有放回 iid 重抽样（教学对照；波动聚类下低估不确定性，
      摘要要求 A 股禁用其作结论依据）。
    返回样本统计量、bootstrap 均值/标准差、percentile 置信区间、
    MC 标准误 σ̂/√b（式 13.3）。
    """
    if method not in ("cbb", "iid"):
        raise ValueError("method must be 'cbb' or 'iid'")
    if n_bootstrap < 2:
        raise ValueError("n_bootstrap must be >= 2")
    if not 0.0 < ci_level < 1.0:
        raise ValueError("ci_level must be in (0, 1)")
    r = pd.Series(returns, dtype=float).dropna()
    if len(r) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} non-NaN returns, got {len(r)}")
    arr = r.to_numpy()
    n = len(arr)
    fn = _metric_fn(metric)
    q = block_size if block_size is not None else default_block_size(n)
    if q < 1:
        raise ValueError("block_size must be >= 1")

    rng = np.random.default_rng(seed)
    if method == "cbb":
        from arch.bootstrap import CircularBlockBootstrap

        bs = CircularBlockBootstrap(q, arr, seed=rng)
        samples = (data[0] for data, _kw in bs.bootstrap(n_bootstrap))
        estimates = np.array([fn(s, annualization_factor, risk_free_rate) for s in samples])
    else:
        estimates = np.array(
            [
                fn(arr[rng.integers(0, n, size=n)], annualization_factor, risk_free_rate)
                for _ in range(n_bootstrap)
            ]
        )

    sample_stat = float(fn(arr, annualization_factor, risk_free_rate))
    boot_std = float(estimates.std(ddof=1))
    alpha = 1.0 - ci_level
    lo, hi = np.quantile(estimates, [alpha / 2.0, 1.0 - alpha / 2.0])
    return {
        "metric": metric,
        "method": method,
        "n_obs": n,
        "n_bootstrap": n_bootstrap,
        "block_size": (q if method == "cbb" else None),
        "ci_level": ci_level,
        "seed": seed,
        "sample_statistic": sample_stat,
        "bootstrap_mean": float(estimates.mean()),
        "bootstrap_std": boot_std,
        "ci_lower": float(lo),
        "ci_upper": float(hi),
        "mc_standard_error": float(boot_std / np.sqrt(n_bootstrap)),
        "risk_free_rate_annual": risk_free_rate,
        "annualization_factor": annualization_factor,
        "note": (
            "CBB 块长 q=ceil(√n) 保留波动聚类（书2 Ch13）；MC 标准误=σ̂/√b（式 13.3）"
            if method == "cbb"
            else "iid bootstrap 破坏时间依赖、波动聚类下低估不确定性（书2 Ch13），"
            "仅作对照，A 股禁用其作结论依据"
        ),
    }


def bootstrap_summary(
    returns: pd.Series | np.ndarray | list[float],
    metrics: tuple[str, ...] = METRIC_NAMES,
    n_bootstrap: int = BOOTSTRAP_REPLICATIONS,
    block_size: int | None = None,
    ci_level: float = BOOTSTRAP_CI_LEVEL,
    seed: int | None = BOOTSTRAP_SEED,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, Any]:
    """多指标汇总：每个指标给 CBB 主结果 + iid 对照。"""
    out: dict[str, Any] = {}
    for metric in metrics:
        cbb = bootstrap_metric_ci(
            returns, metric, "cbb", n_bootstrap, block_size, ci_level,
            seed, risk_free_rate, annualization_factor,
        )
        iid = bootstrap_metric_ci(
            returns, metric, "iid", n_bootstrap, block_size, ci_level,
            seed, risk_free_rate, annualization_factor,
        )
        out[metric] = {
            "cbb": cbb,
            "iid": iid,
            "iid_underestimates": bool(iid["bootstrap_std"] < cbb["bootstrap_std"]),
            "note": "教材（书2 Ch13）：iid 重抽样把高低波动期均衡化，波动聚类下"
            "低估不确定性；以 CBB 为准，iid_std < cbb_std 时 iid_underestimates=True",
        }
    return out
