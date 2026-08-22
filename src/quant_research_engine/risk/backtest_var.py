"""VaR 回测（书2 Ch6）：HIT 序列、覆盖率 LR 检验、独立性检验、多重检验警示。

框架（摘要书2 Ch6）：

- HIT_t = I[L_t > VaR_t]，损失 L = −R 取正号（同 tail.py 约定）；
  p-VaR 定义 Pr(L > VaR) = 1−p（式 6.6）。well-specified 模型的
  HIT ~ iid Bernoulli(1−p)。
- 覆盖率：H0: E[HIT_t] = 1−p。教材给三种方法：① 违约次数精确分布
  （二项检验）；② 频率均值渐近 CLT；③ Bernoulli 似然比检验——
  本模块实现 ①（scipy binomtest 双侧）与 ③（LR ~ χ²₁）。
  摘要声明教材未点名 Kupiec：LR 公式与 Kupiec POF 检验相同，如实标注。
- 独立性：教材只给思路（模型正确时 Pr(连续两次 HIT) = (1−p)²）。
  按标准 Christoffersen 转移矩阵 LR_ind ~ χ²₁ 实现，
  返回值 note 注明出处差异（摘要未点名 Christoffersen）。
- 多重检验假阳性：n 个独立检验名义 α，至少一个假阳性概率 1−(1−α)ⁿ
  （n=10, α=0.05 → 40.1%；n=100 → 99.4%）。

LR 统计量中 0·ln0 按极限 0 处理（x=0 / x=n / 零转移计数单元）。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

_MIN_OBS = 2


def hit_series(
    returns: pd.Series | np.ndarray | list[float],
    var_series: pd.Series | np.ndarray | list[float],
) -> pd.Series:
    """HIT 序列：I_t = 1{L_t > VaR_t}，L_t = −R_t（损失正号，书2 Ch6 式 6.6）。

    输入逐日收益与同日 1 日 VaR（损失口径，正数）；按索引对齐（array 输入
    则按位置对齐），任一侧 NaN 的日期丢弃。返回 int 0/1 序列。
    """
    frame = pd.DataFrame(
        {"r": pd.Series(returns, dtype=float), "var": pd.Series(var_series, dtype=float)}
    ).dropna()
    if len(frame) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} paired non-NaN observations, got {len(frame)}")
    hits = (frame["r"] < -frame["var"]).astype(int)
    return hits.rename("hit")


def coverage_lr_test(
    hits: pd.Series | np.ndarray | list[int],
    confidence: float = 0.99,
) -> dict[str, Any]:
    """覆盖率（无条件覆盖）检验：HIT ~ Bernoulli(1−p) 的似然比检验。

    LR = −2·[(n−x)·ln((1−p)/(1−p̂)) + x·ln(p/p̂)] ~ χ²(1)，
    p = confidence，p̂ = x/n 为违约率 MLE（教材方法③；公式同 Kupiec POF
    检验，摘要声明教材未点名 Kupiec，如实标注）。附精确二项双侧 p 值
    （教材方法①）。x=0/x=n 时 0·ln0 项按极限 0 处理。
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    h = pd.Series(hits, dtype=float).dropna()
    if len(h) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} hits, got {len(h)}")
    if not h.isin([0, 1]).all():
        raise ValueError("hits must be 0/1")
    n = int(len(h))
    x = int(h.sum())
    p = 1.0 - confidence  # H0 下的违约概率（式 6.6：Pr(L>VaR)=1−confidence）
    p_hat = x / n

    log_lr = 0.0
    if n - x > 0 and p_hat < 1.0:
        log_lr += (n - x) * np.log((1.0 - p) / (1.0 - p_hat))
    if x > 0 and p_hat > 0.0:
        log_lr += x * np.log(p / p_hat)
    lr = float(-2.0 * log_lr)
    p_value = float(stats.chi2.sf(lr, 1))
    exact_p = float(stats.binomtest(x, n, p).pvalue)
    return {
        "test": "coverage_lr",
        "confidence": confidence,
        "expected_violation_rate": p,
        "n_obs": n,
        "violations": x,
        "expected_violations": n * p,
        "violation_rate": p_hat,
        "lr_statistic": lr,
        "p_value": p_value,
        "exact_binomial_p_value": exact_p,
        "reject_5pct": bool(p_value < 0.05),
        "dist": "chi2(1)",
        "note": "H0: HIT~Bernoulli(1−p)（书2 Ch6 式 6.6，方法③ LR + 方法① 精确二项）；"
        "LR 公式同 Kupiec POF 检验，摘要声明教材未点名 Kupiec，如实标注",
    }


def independence_lr_test(
    hits: pd.Series | np.ndarray | list[int],
) -> dict[str, Any]:
    """独立性检验：Christoffersen 转移矩阵 LR_ind ~ χ²(1)。

    转移计数 n00/n01/n10/n11；π01 = n01/(n00+n01)、π11 = n11/(n10+n11)、
    π̄ = (n01+n11)/n；
    LR_ind = −2·ln[ (1−π̄)^{n00+n10}·π̄^{n01+n11} /
    ((1−π01)^n00·π01^n01·(1−π11)^n10·π11^n11) ]。

    出处差异（如实标注）：摘要书2 Ch6 只给思路「模型正确时
    E[HIT_t·HIT_{t+1}] = (1−p)²」，未点名 Christoffersen；此处按业界标准
    Christoffersen（1998）一阶 Markov 转移矩阵 LR 实现，零计数单元跳过。
    """
    h = pd.Series(hits, dtype=float).dropna().astype(int)
    if len(h) < _MIN_OBS:
        raise ValueError(f"need at least {_MIN_OBS} hits, got {len(h)}")
    if not h.isin([0, 1]).all():
        raise ValueError("hits must be 0/1")
    arr = h.to_numpy()
    prev, curr = arr[:-1], arr[1:]
    n00 = int(np.sum((prev == 0) & (curr == 0)))
    n01 = int(np.sum((prev == 0) & (curr == 1)))
    n10 = int(np.sum((prev == 1) & (curr == 0)))
    n11 = int(np.sum((prev == 1) & (curr == 1)))

    pi01 = n01 / (n00 + n01) if (n00 + n01) > 0 else 0.0
    pi11 = n11 / (n10 + n11) if (n10 + n11) > 0 else 0.0
    pi_bar = (n01 + n11) / (n00 + n01 + n10 + n11)

    log_null = 0.0
    if (n00 + n10) > 0 and pi_bar < 1.0:
        log_null += (n00 + n10) * np.log(1.0 - pi_bar)
    if (n01 + n11) > 0 and pi_bar > 0.0:
        log_null += (n01 + n11) * np.log(pi_bar)
    log_alt = 0.0
    if n00 > 0 and pi01 < 1.0:
        log_alt += n00 * np.log(1.0 - pi01)
    if n01 > 0 and pi01 > 0.0:
        log_alt += n01 * np.log(pi01)
    if n10 > 0 and pi11 < 1.0:
        log_alt += n10 * np.log(1.0 - pi11)
    if n11 > 0 and pi11 > 0.0:
        log_alt += n11 * np.log(pi11)

    lr = float(-2.0 * (log_null - log_alt))
    p_value = float(stats.chi2.sf(lr, 1))
    return {
        "test": "independence_lr",
        "n_transitions": int(len(arr) - 1),
        "transitions": {"n00": n00, "n01": n01, "n10": n10, "n11": n11},
        "pi_01": pi01,
        "pi_11": pi11,
        "pi_pooled": pi_bar,
        "lr_statistic": lr,
        "p_value": p_value,
        "reject_5pct": bool(p_value < 0.05),
        "dist": "chi2(1)",
        "note": "Christoffersen(1998) 一阶 Markov 转移矩阵 LR；摘要书2 Ch6 只给思路 "
        "E[HIT_t·HIT_{t+1}]=(1−p)²、未点名 Christoffersen，按业界标准实现并标注差异",
    }


def false_positive_probability(alpha: float, n_tests: int) -> float:
    """n 个独立检验名义 α 下至少一个假阳性的概率：1−(1−α)ⁿ（书2 Ch6）。

    例：α=0.05, n=10 → 0.4013；n=100 → 0.9941（量化过拟合核心警示）。
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if n_tests < 1:
        raise ValueError("n_tests must be >= 1")
    return float(1.0 - (1.0 - alpha) ** n_tests)


def backtest_var_summary(
    returns: pd.Series | np.ndarray | list[float],
    var_series: pd.Series | np.ndarray | list[float],
    confidence: float = 0.99,
) -> dict[str, Any]:
    """VaR 回测统一入口：HIT + 覆盖率 + 独立性 + 结论。"""
    hits = hit_series(returns, var_series)
    coverage = coverage_lr_test(hits, confidence)
    independence = independence_lr_test(hits)
    passed = not coverage["reject_5pct"] and not independence["reject_5pct"]
    if coverage["reject_5pct"] and independence["reject_5pct"]:
        conclusion = "覆盖率与独立性均在 5% 拒绝：VaR 模型两方面都失配"
    elif coverage["reject_5pct"]:
        conclusion = "覆盖率 5% 拒绝：违约频率偏离 1−p"
    elif independence["reject_5pct"]:
        conclusion = "独立性 5% 拒绝：HIT 聚集（A 股波动聚类下常见，常先于覆盖率挂）"
    else:
        conclusion = "5% 水平不拒绝：覆盖率与独立性均无显著失配证据"
    return {
        "confidence": confidence,
        "n_obs": int(len(hits)),
        "violations": coverage["violations"],
        "expected_violations": coverage["expected_violations"],
        "violation_rate": coverage["violation_rate"],
        "coverage": coverage,
        "independence": independence,
        "reject_5pct": not passed,
        "conclusion": conclusion,
        "note": "书2 Ch6 框架；不拒绝 ≠ 模型正确（证据不足），需结合经济量级判断",
    }
