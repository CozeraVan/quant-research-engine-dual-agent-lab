"""FRM 风险管理分析包（R1 + R2）。

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
"""

from quant_research_engine.risk import (
    backtest_var,
    constants,
    dependence,
    inference,
    performance,
    report,
    stress,
    tail,
    volatility,
)

__all__ = [
    "backtest_var",
    "constants",
    "dependence",
    "inference",
    "performance",
    "report",
    "stress",
    "tail",
    "volatility",
]
