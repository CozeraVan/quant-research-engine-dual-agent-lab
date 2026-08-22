"""收益换算与依赖结构：simple/log 换算、Spearman/Kendall、正定性检查。

- simple↔log（书2 Ch12 式 12.5）：1 + R = e^r，即 r = log1p(R)、R = expm1(r)。
- Spearman（式 12.13）/ Kendall（式 12.14）秩相关：scipy.stats。
- 相关矩阵正定性（书2 Ch12）：最小特征值 > tol → positive definite。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

_MIN_OBS = 3
_PD_TOL = 1e-8


def _clean_pair(
    x: pd.Series | np.ndarray | list[float],
    y: pd.Series | np.ndarray | list[float],
) -> tuple[pd.Series, pd.Series]:
    frame = pd.DataFrame({"x": pd.Series(x, dtype=float), "y": pd.Series(y, dtype=float)}).dropna()
    if len(frame) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} paired non-NaN observations, got {len(frame)}")
    return frame["x"], frame["y"]


def simple_to_log_returns(
    returns: pd.Series | np.ndarray | list[float],
) -> pd.Series:
    """simple → log 收益：r = ln(1+R)（书2 Ch12 式 12.5）。"""
    r = pd.Series(returns, dtype=float)
    if (r <= -1.0).any():
        raise ValueError("simple returns must be > -1 (1+R > 0) for log conversion")
    return pd.Series(np.log1p(r.to_numpy()), index=r.index, name="log_return")


def log_to_simple_returns(
    log_returns: pd.Series | np.ndarray | list[float],
) -> pd.Series:
    """log → simple 收益：R = e^r − 1（书2 Ch12 式 12.5）。"""
    r = pd.Series(log_returns, dtype=float)
    return pd.Series(np.expm1(r.to_numpy()), index=r.index, name="simple_return")


def spearman_corr(
    x: pd.Series | np.ndarray | list[float],
    y: pd.Series | np.ndarray | list[float],
) -> dict[str, Any]:
    """Spearman 秩相关（书2 Ch12 式 12.13；并列取平均秩，scipy 口径）。"""
    xs, ys = _clean_pair(x, y)
    coefficient, pvalue = stats.spearmanr(xs, ys)
    return {
        "method": "spearman",
        "coefficient": float(coefficient),
        "p_value": float(pvalue),
        "n_obs": int(len(xs)),
        "note": "式 12.13 ρS=1−6Σd²/(n(n²−1))（秩互异时）；单调变换不变，对异常值稳健",
    }


def kendall_corr(
    x: pd.Series | np.ndarray | list[float],
    y: pd.Series | np.ndarray | list[float],
) -> dict[str, Any]:
    """Kendall's τ（书2 Ch12 式 12.14，scipy.stats.kendalltau）。"""
    xs, ys = _clean_pair(x, y)
    coefficient, pvalue = stats.kendalltau(xs, ys)
    return {
        "method": "kendall",
        "coefficient": float(coefficient),
        "p_value": float(pvalue),
        "n_obs": int(len(xs)),
        "note": "式 12.14 τ=(nc−nd)/(nc+nd+nt)；单调变换不变",
    }


def is_positive_definite(
    matrix: pd.DataFrame | np.ndarray,
    tol: float = _PD_TOL,
) -> dict[str, Any]:
    """相关/协方差矩阵正定性检查（书2 Ch12）：最小特征值 > tol → PD。"""
    arr = matrix.to_numpy(dtype=float) if isinstance(matrix, pd.DataFrame) else np.asarray(matrix, dtype=float)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        raise ValueError("matrix must be square")
    if not np.allclose(arr, arr.T, atol=1e-10):
        raise ValueError("matrix must be symmetric")
    eigenvalues = np.linalg.eigvalsh(arr)
    min_eigenvalue = float(eigenvalues[0])
    return {
        "positive_definite": bool(min_eigenvalue > tol),
        "min_eigenvalue": min_eigenvalue,
        "tol": tol,
        "n": int(arr.shape[0]),
        "note": "任何线性组合方差 ≥0 要求相关矩阵 positive definite（书2 Ch12）",
    }
