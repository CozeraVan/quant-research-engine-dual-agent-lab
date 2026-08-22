"""尾部风险度量：VaR/ES 三口径 + 分布矩 + 正态性检验。

损失取正号约定（书4 Ch1）：输入为 simple 收益序列，损失 L = −R。

- 参数正态（书4 Ch1 式 1.7）：VaR = μ + σ·z，ES = μ + σ·φ(z)/(1−X)。
  教材例题：μ=−20, σ=30, X=99% → VaR=49.79, ES=59.96。
- 历史模拟（书4 Ch2）：损失升序取分位（numpy linear 插值，披露）；
  ES = 不低于 VaR 的损失均值（含 VaR 本身，保证 ES ≥ VaR 恒成立）。
- EWMA 参数法：σ 取 EWMA 最新次日预测（volatility.ewma_variance_series），
  μ 取样本均值，套同一正态公式。
- 偏度/峰度（书2 Ch5）：sample analog（1/n 口径）与 n−1 小样本校正版
  （= scipy bias=False）双口径。
- Jarque-Bera（书2 Ch12 式 12.11）：教材用 (T−1)，scipy.stats.jarque_bera
  用 T，差异在返回值 note 中披露。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from quant_research_engine.risk.constants import ANNUALIZATION_FACTOR, EWMA_LAMBDA, z_value

_MIN_OBS = 2


def _clean_returns(returns: pd.Series | np.ndarray | list[float]) -> pd.Series:
    series = pd.Series(returns, dtype=float).dropna()
    if len(series) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} non-NaN returns, got {len(series)}")
    return series


def parametric_normal_var_es(
    returns: pd.Series | np.ndarray | list[float],
    confidence: float = 0.99,
) -> dict[str, Any]:
    """参数正态 VaR/ES（书4 Ch1 式 1.7，损失口径）。"""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    r = _clean_returns(returns)
    loss = -r
    mu = float(loss.mean())
    sigma = float(loss.std(ddof=1))
    z = z_value(confidence)
    var = mu + sigma * z
    es = mu + sigma * float(stats.norm.pdf(z)) / (1.0 - confidence)
    return {
        "method": "parametric_normal",
        "confidence": confidence,
        "z": z,
        "loss_mean": mu,
        "loss_std": sigma,
        "var": var,
        "es": es,
        "annualization_factor": ANNUALIZATION_FACTOR,
        "note": "损失 L=−R 正态假设；VaR=μ+σz，ES=μ+σφ(z)/(1−X)（书4 Ch1 式 1.7）",
    }


def historical_var_es(
    returns: pd.Series | np.ndarray | list[float],
    confidence: float = 0.99,
    interpolation: str = "linear",
) -> dict[str, Any]:
    """历史模拟 VaR/ES（书4 Ch2，有序统计量 + 线性插值）。"""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    r = _clean_returns(returns)
    losses = np.sort((-r).to_numpy())
    var = float(np.quantile(losses, confidence, method=interpolation))
    tail = losses[losses >= var]
    es = float(tail.mean()) if len(tail) > 0 else var
    return {
        "method": "historical_simulation",
        "confidence": confidence,
        "n_obs": int(len(losses)),
        "interpolation": interpolation,
        "var": var,
        "es": es,
        "tail_count": int(len(tail)),
        "annualization_factor": ANNUALIZATION_FACTOR,
        "note": "损失升序分位（numpy 线性插值）；ES=不低于 VaR 的损失均值（含 VaR，ES≥VaR 恒成立）",
    }


def ewma_parametric_var_es(
    returns: pd.Series | np.ndarray | list[float],
    confidence: float = 0.99,
    lam: float = EWMA_LAMBDA,
) -> dict[str, Any]:
    """EWMA 参数法 VaR/ES：σ 取 EWMA 次日预测，正态公式同书4 Ch1 式 1.7。"""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    from quant_research_engine.risk.volatility import ewma_variance_series

    r = _clean_returns(returns)
    variance = ewma_variance_series(r, lam=lam)
    sigma = float(np.sqrt(variance.iloc[-1]))
    mu = float((-r).mean())
    z = z_value(confidence)
    var = mu + sigma * z
    es = mu + sigma * float(stats.norm.pdf(z)) / (1.0 - confidence)
    return {
        "method": "ewma_parametric",
        "confidence": confidence,
        "lambda": lam,
        "z": z,
        "loss_mean": mu,
        "sigma_forecast": sigma,
        "var": var,
        "es": es,
        "annualization_factor": ANNUALIZATION_FACTOR,
        "note": "σ=EWMA(λ) 次日条件波动预测（书4 Ch3 式 3.2，raw 序列末值），μ=样本均值；正态公式同式 1.7",
    }


def skew_kurtosis(
    returns: pd.Series | np.ndarray | list[float],
) -> dict[str, Any]:
    """偏度/峰度双口径（书2 Ch5）。

    - sample analog：ŝ = μ̂3/σ̂³、k̂ = μ̂4/σ̂⁴（1/n 口径，σ̂ 用 1/n 标准差）
      ——与 scipy.stats.skew/kurtosis(bias=True) 一致。
    - bias-corrected：n−1 小样本校正版 —— scipy bias=False。
    峰度同时给 raw（正态=3）与 excess（正态=0）。
    """
    r = _clean_returns(returns)
    arr = r.to_numpy()
    skew_sample = float(stats.skew(arr, bias=True))
    kurt_sample = float(stats.kurtosis(arr, bias=True, fisher=False))
    return {
        "n_obs": int(len(arr)),
        "skew_sample": skew_sample,
        "kurtosis_sample": kurt_sample,
        "excess_kurtosis_sample": kurt_sample - 3.0,
        "skew_bias_corrected": float(stats.skew(arr, bias=False)),
        "kurtosis_bias_corrected": float(stats.kurtosis(arr, bias=False, fisher=False)),
        "excess_kurtosis_bias_corrected": float(stats.kurtosis(arr, bias=False, fisher=True)),
        "note": "sample=μ̂3/σ̂³、μ̂4/σ̂⁴（1/n，书2 Ch5）；bias_corrected=scipy bias=False（n−1 校正）",
    }


def jarque_bera_test(
    returns: pd.Series | np.ndarray | list[float],
) -> dict[str, Any]:
    """Jarque-Bera 正态性检验（书2 Ch12 式 12.11，χ²(2)）。"""
    r = _clean_returns(returns)
    result = stats.jarque_bera(r.to_numpy())
    statistic = float(result.statistic)
    return {
        "jb_statistic": statistic,
        "p_value": float(result.pvalue),
        "n_obs": int(len(r)),
        "reject_normal_5pct": bool(result.pvalue < 0.05),
        "critical_5pct": 5.99,
        "critical_1pct": 9.21,
        "note": "教材式 12.11 用 (T−1)，scipy.stats.jarque_bera 用 T；大样本差异可忽略，此处为 scipy 口径",
    }


def distribution_summary(
    returns: pd.Series | np.ndarray | list[float],
) -> dict[str, Any]:
    """收益分布摘要：矩 + JB + 稳健分位对照（书2 Ch5 落地提示）。"""
    r = _clean_returns(returns)
    arr = r.to_numpy()
    moments = skew_kurtosis(r)
    jb = jarque_bera_test(r)
    return {
        "n_obs": int(len(arr)),
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "median": float(np.median(arr)),
        "q25": float(np.quantile(arr, 0.25)),
        "q75": float(np.quantile(arr, 0.75)),
        "iqr": float(np.quantile(arr, 0.75) - np.quantile(arr, 0.25)),
        **{k: moments[k] for k in moments if k not in {"n_obs", "note"}},
        "jb_statistic": jb["jb_statistic"],
        "jb_p_value": jb["p_value"],
        "reject_normal_5pct": jb["reject_normal_5pct"],
        "annualization_factor": ANNUALIZATION_FACTOR,
        "note": moments["note"] + "；" + jb["note"],
    }
