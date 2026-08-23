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

#: 晋升闸风险判据（R4）：99% ES（日收益损失口径，历史模拟）上限，
#: 超过则闸的 risk 维度记 warning（与 failed 同效阻止日更，force 可覆盖）
GATE_ES99_MAX = 0.03

#: 晋升闸 VaR 回测试用置信水平（取 var_backtest 对应节的覆盖率
#: Kupiec LR 检验，5% 显著被拒绝 → warning；与 ES99 同置信）
GATE_VAR_CONFIDENCE = 0.99


#: 债券应计利息默认 day count（中国债券惯例 actual/actual，CR §4 约束；
#: 参数化可选 "30/360"，见书3 Ch17 公司债惯例）
DEFAULT_DAY_COUNT = "actual/actual"

#: 零息曲线默认插值方式（"linear"=零息利率线性插值；
#: "log_linear"=折现因子对数线性插值，即远期利率分段常数）
CURVE_INTERPOLATION = "linear"

#: Key rate 节点（年；书4 Ch13，覆盖短中长腿与 FRTB 10 节点口径的常用子集）
KEY_RATE_TENORS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0)

#: 利率扰动步长（bp）：effective duration/convexity、DV01、KR01、
#: spread duration 的 ±Δr 重定价统一用 1bp
RATE_SHOCK_BP = 1.0

#: YTM 反解的 brentq 搜索区间（年化收益率，-5% ~ 100%；书4 Ch11 迭代求解）
YTM_BRACKET: tuple[float, float] = (-0.05, 1.0)

#: 隐含波动率反解的 brentq 搜索区间（年化波动率，书4 Ch15 successive bisection）
IV_BRACKET: tuple[float, float] = (1e-4, 5.0)

#: CRR 二叉树默认步数（书4 Ch14：实务至少 30–50 步）
DEFAULT_TREE_STEPS = 50

#: 美式 Greeks 数值差分的微扰步长（书4 Ch16：vega/rho 微扰重建树）：
#: σ 扰动（绝对，1e-4 = 0.01%）与 r 扰动（绝对，1e-4 = 1bp）
GREEK_SHOCK_SIGMA = 1e-4
GREEK_SHOCK_RATE = 1e-4


def default_block_size(n_obs: int) -> int:
    """CBB 块长经验法则 q ≈ √n（书2 Ch13），向上取整、至少为 1。"""
    if n_obs < 1:
        raise ValueError("n_obs must be >= 1")
    return max(1, int(np.ceil(np.sqrt(n_obs))))
