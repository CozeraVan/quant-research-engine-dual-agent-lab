"""risk 包集中常量（A 股口径，见 docs/frm/CR_2026-08-21_frm_risk_module.md §4）。

每个结果 dict 都回显所用参数，保证报告可审计、可复现。
"""

from __future__ import annotations

from scipy import stats

#: 年化交易日数（A 股口径；教材书2 Ch5：惯例随市场而异，关键是项目内自洽）
ANNUALIZATION_FACTOR = 252

#: 默认置信水平（VaR/ES 两口径同时报告）
CONFIDENCE_LEVELS: tuple[float, ...] = (0.95, 0.99)

#: EWMA 衰减因子 λ（书4 Ch3 式 3.2，RiskMetrics 日频推荐 0.94）
EWMA_LAMBDA = 0.94

#: 默认无风险利率（年化，simple 口径）
DEFAULT_RISK_FREE_RATE = 0.03

#: 波动率 regime 分位（低/中/高三分位，规则写死并披露）
REGIME_QUANTILES: tuple[float, float] = (1.0 / 3.0, 2.0 / 3.0)

#: 正态分位点（scipy 精确值；教材书4 Ch1 记 1.645 / 2.326）
Z_95 = float(stats.norm.ppf(0.95))  # 1.6448536269514722
Z_99 = float(stats.norm.ppf(0.99))  # 2.3263478740408408


def z_value(confidence: float) -> float:
    """置信水平 X → 标准正态上尾点 z（损失为正号约定）。"""
    return float(stats.norm.ppf(confidence))
