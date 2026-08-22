"""risk 包集中常量（A 股口径，见 docs/frm/CR_2026-08-21_frm_risk_module.md §4）。

每个结果 dict 都回显所用参数，保证报告可审计、可复现。
"""

from __future__ import annotations

import numpy as np
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


#: 历史压力情景库（书4 Ch8 historical scenarios，A 股口径；窗口参数化可增删）。
#: 键 = 情景名，值 = (起始日, 结束日, 说明)。日期为闭区间，与交易日对齐时取交集。
HISTORICAL_SCENARIOS: dict[str, tuple[str, str, str]] = {
    "crash_2015": ("2015-06-15", "2015-09-30", "2015 股灾：千股跌停 + 流动性枯竭"),
    "bear_2018": ("2018-01-01", "2018-12-31", "2018 单边熊市"),
    "covid_2020": ("2020-01-20", "2020-03-31", "2020 疫情跳空"),
    "microcap_liquidity_2024": ("2024-01-01", "2024-02-29", "2024 小微盘流动性危机"),
}

#: reverse stress 默认滚动窗口（交易日，约一个月）
REVERSE_STRESS_HORIZON = 21

#: Circular Block Bootstrap 默认重抽样次数（书2 Ch13；误差 ∝ 1/√b）
BOOTSTRAP_REPLICATIONS = 1000

#: Bootstrap 默认置信水平（区间取 (α/2, 1−α/2) 分位）
BOOTSTRAP_CI_LEVEL = 0.95

#: Bootstrap 默认随机种子（教材强调可复现性/监管合规；None = 不固定）
BOOTSTRAP_SEED = 42


def default_block_size(n_obs: int) -> int:
    """CBB 块长经验法则 q ≈ √n（书2 Ch13），向上取整、至少为 1。"""
    if n_obs < 1:
        raise ValueError("n_obs must be >= 1")
    return max(1, int(np.ceil(np.sqrt(n_obs))))
