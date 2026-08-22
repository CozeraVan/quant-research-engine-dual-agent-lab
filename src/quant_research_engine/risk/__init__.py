"""FRM 风险管理分析包（R1 + R2 + R5）。

纯函数 + pandas/numpy/arch/scipy，不读 DB、不依赖 QRE 内部状态，
可被 cluster-ashare 等外部项目独立 import。

公式与参数一律以 ``docs/frm/FRM量化风控知识摘要.md`` 为准：

- tail.py：VaR/ES 三口径（历史模拟/参数正态/EWMA 参数法，损失取正号，
  书4 Ch1/Ch2）、偏度/峰度（书2 Ch5）、Jarque-Bera（书2 Ch12 式 12.11）。
- volatility.py：EWMA（书4 Ch3 式 3.2，RiskMetrics λ=0.94）、
  GARCH(1,1)（式 3.4，V_L=ω/(1−α−β)）、波动率 regime 标记。
- dependence.py：Spearman/Kendall 秩相关（书2 Ch12 式 12.13/12.14）、
  相关矩阵正定性检查、simple/log 收益换算（式 12.5）。
- performance.py：Sharpe/Treynor/Sortino/IR/Jensen's α（书1 Ch5）。
- backtest_var.py：VaR 回测（书2 Ch6）——HIT 序列、覆盖率 Bernoulli LR
  检验、独立性 Christoffersen 转移矩阵 LR、多重检验假阳性警示。
- stress.py：压力测试（书4 Ch8）——历史情景库回放（累计损失/峰谷/
  Peak/VaR）、reverse stress（β 穿透反查市场冲击分位/σ 倍数）、
  相关性崩溃提示。
- inference.py：Bootstrap 推断（书2 Ch13）——CBB（块长 √n）与 iid 对照
  给年化收益/夏普/最大回撤算置信区间，MC 标准误 σ/√b。
- report.py：``build_risk_report`` 机读报告骨架（markdown 渲染留 R3）。
- rates.py（R5）：复利换算（书3 Ch16 式 16.1–16.5）、PV/FV、spot↔折现因子、
  附息债 bootstrap 零息曲线（书4 Ch9）、远期利率、par yield（式 16.7/10.4）。
- bonds.py（R5）：YTM（brentq，书4 Ch11）、dirty/clean 与应计利息（式 9.2）、
  Macaulay/Modified duration、yield/effective convexity、DV01（书4 Ch12）、
  组合聚合与 DV01 对冲、平行移动二阶近似（式 12.4）、KR01（书4 Ch13）、
  可转债债底折现与 spread duration（书3 Ch16/17）。
"""

from quant_research_engine.risk import (
    backtest_var,
    bonds,
    constants,
    dependence,
    inference,
    performance,
    rates,
    report,
    stress,
    tail,
    volatility,
)

__all__ = [
    "backtest_var",
    "bonds",
    "constants",
    "dependence",
    "inference",
    "performance",
    "rates",
    "report",
    "stress",
    "tail",
    "volatility",
]
