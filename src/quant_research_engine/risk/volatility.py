"""波动率建模：EWMA、GARCH(1,1)、波动率 regime 标记。

- EWMA（书4 Ch3 式 3.2）：σ²_n = λ·σ²_{n−1} + (1−λ)·r²_n（raw 口径，
  day-n 收盘后估计 = 次日预测），λ=0.94（RiskMetrics 日频推荐）。初始化
  σ²_1 = r²_1（披露）。point-in-time 对齐用 ewma_forecast_series
  （raw.shift(1)，day-t 仅用 ≤t−1 数据，防前视）。
- GARCH(1,1)（式 3.4）：σ²_n = ω + α·r²_{n−1} + β·σ²_{n−1}；arch 拟合
  （收益 ×100 拟合后 ÷100² 还原方差参数，arch 官方数值稳定性惯例）；
  V_L = ω/(1−α−β)，半衰期 ln(0.5)/ln(α+β)，α+β<1 为协方差平稳。
- regime 标记：分位规则写死（默认 1/3、2/3）并披露。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.risk.constants import EWMA_LAMBDA, REGIME_QUANTILES

_MIN_OBS = 2
_GARCH_MIN_OBS = 50


def ewma_variance_series(
    returns: pd.Series | np.ndarray | list[float],
    lam: float = EWMA_LAMBDA,
) -> pd.Series:
    """EWMA 条件方差序列（raw 口径：day-n 值纳入 r_n）。

    递推：σ²_1 = r²_1（初始化约定）；σ²_n = λ·σ²_{n−1} + (1−λ)·r²_n。
    day-n 值 = 收盘后的方差估计，即对 day n+1 的预测；序列末值即次日预测。
    **point-in-time 对齐必须 shift(1)**（用 ewma_forecast_series），否则前视。
    手算核对（r=[0.01,−0.02,0.03]，λ=0.94）→ σ²=[1e-4, 1.18e-4, 1.6492e-4]；
    与 arch（固定参数 ω=0, α=1−λ, β=λ 的 GARCH 递归，shift(1) 后）一致到 1e-12。
    """
    if not 0.0 < lam < 1.0:
        raise ValueError("lam must be in (0, 1)")
    r = pd.Series(returns, dtype=float).dropna()
    if len(r) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} non-NaN returns, got {len(r)}")
    arr = r.to_numpy()
    var = np.empty(len(arr), dtype=float)
    var[0] = arr[0] ** 2
    for i in range(1, len(arr)):
        var[i] = lam * var[i - 1] + (1.0 - lam) * arr[i] ** 2
    return pd.Series(var, index=r.index, name="ewma_variance")


def ewma_forecast_series(
    returns: pd.Series | np.ndarray | list[float],
    lam: float = EWMA_LAMBDA,
) -> pd.Series:
    """EWMA 方差 point-in-time 序列：raw.shift(1)，day-t 值仅用 r_1..r_{t−1}。

    用于 rolling VaR/回测对齐（防前视）；首值无历史可用被丢弃。
    """
    return ewma_variance_series(returns, lam=lam).shift(1).dropna().rename("ewma_variance_forecast")


def ewma_volatility_series(
    returns: pd.Series | np.ndarray | list[float],
    lam: float = EWMA_LAMBDA,
) -> pd.Series:
    """EWMA 条件波动率序列（ewma_variance_series 开根）。"""
    return np.sqrt(ewma_variance_series(returns, lam=lam)).rename("ewma_volatility")


def latest_ewma_forecast(
    returns: pd.Series | np.ndarray | list[float],
    lam: float = EWMA_LAMBDA,
) -> dict[str, Any]:
    """EWMA 最新次日波动预测（序列末值）。"""
    variance = ewma_variance_series(returns, lam=lam)
    return {
        "lambda": lam,
        "n_obs": int(len(variance)),
        "variance_forecast": float(variance.iloc[-1]),
        "volatility_forecast": float(np.sqrt(variance.iloc[-1])),
        "init": "sigma2_1 = r1^2",
        "alignment": "raw 口径 day-n 值纳入 r_n（收盘后估计）；末值 = 次日 σ² 预测；rolling 对齐需 shift(1)",
        "note": "书4 Ch3 式 3.2，RiskMetrics λ=0.94",
    }


def fit_garch11(
    returns: pd.Series | np.ndarray | list[float],
) -> dict[str, Any]:
    """GARCH(1,1) 拟合（正态创新，arch；书4 Ch3 式 3.4）。

    收益 ×100 拟合后 ÷100² 还原 ω/V_L（arch 官方数值稳定性惯例）；
    α、β 无量纲不缩放。返回 ω/α/β、α+β、平稳标志、V_L、半衰期
    ln(0.5)/ln(α+β)、最新条件波动。
    """
    from arch import arch_model

    r = pd.Series(returns, dtype=float).dropna()
    if len(r) < _GARCH_MIN_OBS:
        raise ValueError(f"need at least {_GARCH_MIN_OBS} non-NaN returns for GARCH, got {len(r)}")
    scaled = r.to_numpy() * 100.0
    model = arch_model(scaled, mean="Zero", vol="GARCH", p=1, q=1, dist="normal")
    fit = model.fit(disp="off")
    params = fit.params
    omega = float(params["omega"]) / (100.0**2)
    alpha = float(params["alpha[1]"])
    beta = float(params["beta[1]"])
    persistence = alpha + beta
    stationary = bool(persistence < 1.0)
    long_run_variance = omega / (1.0 - persistence) if stationary else None
    half_life = float(np.log(0.5) / np.log(persistence)) if 0.0 < persistence < 1.0 else None
    latest_cond_vol = float(fit.conditional_volatility[-1]) / 100.0
    return {
        "model": "GARCH(1,1)",
        "dist": "normal",
        "n_obs": int(len(r)),
        "omega": omega,
        "alpha": alpha,
        "beta": beta,
        "persistence": persistence,
        "stationary": stationary,
        "long_run_variance": long_run_variance,
        "long_run_volatility": (float(np.sqrt(long_run_variance)) if long_run_variance is not None else None),
        "half_life_days": half_life,
        "latest_conditional_volatility": latest_cond_vol,
        "log_likelihood": float(fit.loglikelihood),
        "converged": bool(fit.convergence_flag == 0),
        "note": "式 3.4 σ²=ω+αr²+βσ²；收益×100 拟合 ÷100² 还原；V_L=ω/(1−α−β)；半衰期 ln(0.5)/ln(α+β)",
    }


def volatility_regime(
    volatility: pd.Series | np.ndarray | list[float],
    quantiles: tuple[float, float] = REGIME_QUANTILES,
) -> pd.Series:
    """波动率 regime 标记（low/mid/high，按自身样本分位切分）。

    规则写死：σ < q_low → 'low'；q_low ≤ σ < q_high → 'mid'；≥ q_high → 'high'。
    """
    vol = pd.Series(volatility, dtype=float).dropna()
    if len(vol) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} non-NaN volatilities, got {len(vol)}")
    q_low, q_high = float(np.quantile(vol, quantiles[0])), float(np.quantile(vol, quantiles[1]))
    labels = pd.Series("mid", index=vol.index, name="volatility_regime")
    labels[vol < q_low] = "low"
    labels[vol >= q_high] = "high"
    return labels
