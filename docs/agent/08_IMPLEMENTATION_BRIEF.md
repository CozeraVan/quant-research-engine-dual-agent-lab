# Implementation Brief

## Task ID

QRE-RISK-CORE-001（FRM 风险管理模块 R1：risk 包核心 tail/volatility/dependence/performance + 报告骨架）

## Created By

KIMI_CODE（用户 2026-08-21 直接指定的任务书；依据已批准 CR `docs/frm/CR_2026-08-21_frm_risk_module.md` R1 阶段）

## Intended Implementer

KIMI_CODE

## Goal

落地 FRM 风险模块 R1：新包 `src/quant_research_engine/risk/`，**纯函数 +
pandas/numpy，不读 DB、不依赖 QRE 内部状态**——未来要被 cluster-ashare
股票池项目独立 import（用户明确的最终目标）。四个模块 + 报告骨架：

1. `risk/tail.py`：VaR/ES 三口径（历史模拟有序统计量、参数正态、EWMA 参数法）
   + 偏度/峰度 + JB 正态检验 + 分布摘要。损失取正号约定（教材书4 Ch1）。
2. `risk/volatility.py`：EWMA 波动率序列（λ=0.94，RiskMetrics 递推）；
   GARCH(1,1) 拟合（arch，α+β<1 平稳性检查、V_L=ω/(1−α−β)、半衰期）；
   波动率 regime 简单标记（分位规则写死并披露）。
3. `risk/dependence.py`：Spearman/Kendall 秩相关（scipy）、相关矩阵正定性
   检查（特征值）、simple/log 收益换算。
4. `risk/performance.py`：Sharpe/Treynor/Sortino/IR/Jensen's α（书1 Ch5 公式；
   Sharpe 口径与引擎 `portfolio/risk.py` 一致：(mean(r−rf/252)/std)·√252）。
5. `risk/report.py`：`build_risk_report(returns, benchmark=None, config=None)
   -> dict` 机读骨架（markdown 渲染留 R3）。

## Semantics（公式一律以 `docs/frm/FRM量化风控知识摘要.md` 为准）

- 参数正态 VaR = μ + σ·z_X，ES = μ + σ·φ(z_X)/(1−X)（损失口径；z_95=1.64485，
  z_99=2.32635）。教材例题：μ=−20, σ=30, X=99% → VaR=49.79, ES=59.96
  （书4 Ch1 式 1.7）——作为解析值单测。
- 历史模拟：损失升序后取有序统计量/线性插值分位；ES = 超 VaR 损失均值。
  方法写进返回 dict（插值方法披露）。
- EWMA：σ²_n = λ·σ²_{n−1} + (1−λ)·r²_{n−1}（式 3.2），λ=0.94（RiskMetrics
  日频推荐）；初始化 σ²_1 = r²_1 并披露；序列按「day t 的值仅用 ≤t−1 数据」
  对齐（自带 shift(1) 防前视语义）；最新值即次日 σ 预测。
- GARCH(1,1)：σ²_n = ω + α·r²_{n−1} + β·σ²_{n−1}（式 3.4）；用 arch 拟合
  （收益 ×100 拟合后 ÷100² 还原方差，arch 官方数值稳定性惯例）；返回
  ω/α/β、α+β、平稳标志、V_L、半衰期 ln(0.5)/ln(α+β)、最新条件波动。
- 偏度/峰度：教材 sample analog（μ̂3/σ̂³、μ̂4/σ̂⁴，1/n 口径）与
  n−1 小样本校正版（= scipy bias=False）双口径；JB = scipy.stats.jarque_bera
  （χ²(2)，教材式 12.11 用 T−1，scipy 用 T，差异披露）。
- 秩相关：scipy.stats.spearmanr / kendalltau（式 12.13/12.14）。
- 正定性：相关矩阵最小特征值 > tol → positive definite（书2 Ch12）。
- 绩效：Sharpe=(E[R]−r)/σ、Treynor=(E[R]−r)/β、Sortino=(R_p−T)/ downside
  dev、TE=std(R_p−R_b)、IR=mean(active)/TE、Jensen α = 市场模型回归截距
  （日频 α 与 ×252 年化均报）；β=cov(R_i,R_M)/σ²_M。
- 常量集中 `risk/constants.py`：年化 252、置信水平 95%/99%、λ=0.94、
  默认 rf=3%/年、regime 分位 (1/3, 2/3)；每个结果 dict 携带所用参数。

## Scope

1. `src/quant_research_engine/risk/`：`__init__.py`、`constants.py`、`tail.py`、
   `volatility.py`、`dependence.py`、`performance.py`、`report.py`。
2. `pyproject.toml`：新增依赖 `arch`、`scipy`（CR §7 已定）；`uv sync`。
3. `tests/test_risk_tail.py`、`test_risk_volatility.py`、`test_risk_dependence.py`、
   `test_risk_performance.py`、`test_risk_report.py`。
4. docs/agent 08/10/09/05/11 同步。

## Non-Goals

- 不 git commit、不重启 qre-gui.service。
- 不做 R2（HIT/LR 回测、压力测试、CBB bootstrap）与 R3（markdown 渲染、
  回测报告集成、GUI 展示区）。
- 不改回测引擎 / portfolio/risk.py 既有口径；不读 DB。
- 不做 Cornish-Fisher、GARCH-t（arch 支持但 R1 固定正态创新，留后续）。

## Expected Tests

- 参数正态 VaR/ES 对教材解析值（49.79/59.96 @99%；95% z=1.645 口径）。
- 历史模拟：构造已知损失序列核对第 k 大损失与 ES 均值；ES ≥ VaR 恒成立。
- EWMA 递推手算 3 步核对（r=[0.01,−0.02,0.03]，λ=0.94 →
  σ²=[1e-4, 1.18e-4, 1.6492e-4]）；与 arch EWMA/RiskMetrics 交叉。
- GARCH：arch 模拟已知 (ω,α,β) 数据 → 拟合 α+β sane 范围（~0.9–1.0）、
  平稳标志、V_L>0、半衰期正且量级合理（股权类 ~数十天）；不平稳输入
  （α+β≥1 模拟）→ stationary=False。
- 偏度/峰度对 scipy（bias=True/False 两口径）；正态样本 JB 不拒绝、
  厚尾样本 JB 拒绝。
- Spearman/Kendall 对手算小样本（x=[1,2,3], y=[1,3,2] → ρS=0.5, τ=1/3）。
- 正定性：equicorrelation PD 通过；[[1,2],[2,1]] 非 PD 拒绝。
- simple↔log 换算往返一致（log1p/expm1）。
- Sharpe/Sortino/Treynor/IR/Jensen 对手算值（固定小样本手工核算）；
  Sharpe 与引擎 portfolio/risk.py 口径一致性抽查（同输入同值）。
- regime 标记：平静/高波合成序列 → 规则标签正确。
- report：build_risk_report 结构键齐全、参数回显、benchmark=None 时
  基准相关节为 null 而不报错。
- `uv run pytest tests/ -x -q` 全绿（基线 1471，只增不红）。

## Validation

1. `uv run pytest tests/ -x -q`
2. `scripts/check-progress-docs.sh`
3. `git diff --check`；`git status` 核对变更清单
