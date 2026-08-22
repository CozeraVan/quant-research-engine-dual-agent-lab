# Implementation Brief

## Task ID

QRE-RISK-CORE-002（FRM 风险管理模块 R2：VaR 回测 + 压力测试 + Bootstrap 推断）

## Created By

KIMI_CODE（用户 2026-08-22 直接指定的任务书；依据已批准 CR `docs/frm/CR_2026-08-21_frm_risk_module.md` R2 阶段；R1 已完成 commit 96db59d）

## Intended Implementer

KIMI_CODE

## Goal

在 R1 risk 包基础上落地 R2 三个模块 + 报告扩展，保持 R1 风格（纯函数、
零 DB、参数集中 constants.py、每个结果 dict 回显参数与口径 note）：

1. `risk/backtest_var.py`（书2 Ch6）：
   - `hit_series(returns, var_series)`：I_t = 1{L_t > VaR_t}（L=−R）。
   - `coverage_lr_test(hits, confidence)`：HIT ~ Bernoulli(1−p) 的 LR 检验，
     LR = −2ln(L(p)/L(p̂)) ~ χ²₁，p̂ = x/n 为违约率 MLE；附精确二项 p 值
     （教材三种方法之①③）。
   - `independence_lr_test(hits)`：Christoffersen 转移矩阵 LR_ind ~ χ²₁
     （摘要声明教材 Ch6 只给思路 E[HIT_t·HIT_{t+1}]=(1−p)²、未点名
     Kupiec/Christoffersen；按标准 Christoffersen 实现并在注释/返回值
     注明出处差异）。
   - `false_positive_probability(alpha, n)` = 1−(1−α)ⁿ（多重检验警示）。
   - `backtest_var_summary(returns, var_series, confidence)`：统一 dict
     （violations、expected、LR/p 值、结论）。
2. `risk/stress.py`（书4 Ch8）：
   - 历史情景库（常量，窗口参数化可增删）：2015 股灾（2015-06~2015-09）、
     2018 单边熊（2018 全年）、2020 疫情（2020-01~2020-03）、
     2024 小微盘流动性危机（2024-01~2024-02）。
   - `replay_scenario`：情景窗口内策略累计损失、峰谷（窗口内最大回撤）、
     Peak/VaR 与 Peak/ES 比值（var-backtesting 口径参考）、基准窗口收益、
     窗口内 vs 全样本相关性变化（相关性崩溃提示，呼应 LTCM 红线）。
   - `reverse_stress`：给定亏损阈值，按 β 穿透反推所需市场冲击，并在基准
     滚动窗口收益分布上给出对应经验分位与 σ 倍数。
3. `risk/inference.py`（书2 Ch13）：
   - `bootstrap_metric_ci`：Circular Block Bootstrap
     （arch.bootstrap.CircularBlockBootstrap，块长默认 ceil(√n)）给
     年化收益/夏普/最大回撤算百分位置信区间；输出 MC 标准误 σ/√b（式 13.3）。
   - iid bootstrap 对照（method="iid"），note 说明波动聚类下 iid 低估
     不确定性（教材式 13.11 后讨论）。
4. `risk/report.py` 扩展：`build_risk_report` 新增三节——
   `var_backtest`（默认开启，VaR 序列默认用 R1 EWMA 预测 σ×z、μ=0
   RiskMetrics 口径，note 披露；亦可 config 显式传入 var_series）、
   `stress`（config `stress=True` 开启，需基准做相关性，无基准时只回放
   策略自身）、`bootstrap`（config `bootstrap=True` 开启，b 与 seed 可配）。
   report_version 升 "R2"。

## Semantics（公式以 `docs/frm/FRM量化风控知识摘要.md` 为准）

- HIT：I_t = 1[L_t > VaR_t]，p-VaR 定义 Pr(L>VaR)=1−p（式 6.6）；
  well-specified 模型 HIT ~ iid Bernoulli(1−p)。
- 覆盖率 LR（Bernoulli 似然比，教材方法③；同 Kupiec 但未点名）：
  LR = −2·[(n−x)·ln((1−p)/(1−p̂)) + x·ln(p/p̂)] ~ χ²₁；x=0 或 x=n 时
  对应项按 0·ln0=0 极限处理。
- 独立性 LR（Christoffersen）：转移计数 n00/n01/n10/n11，
  π01=n01/(n00+n01)、π11=n11/(n10+n11)、π̄=(n01+n11)/n；
  LR_ind = −2·ln[ (1−π̄)^{n00+n10}·π̄^{n01+n11} /
  ((1−π01)^n00·π01^n01·(1−π11)^n10·π11^n11) ] ~ χ²₁；零计数单元跳过。
  注释注明：摘要只给思路（H0: E[HIT_t·HIT_{t+1}]=(1−p)²），未点名
  Christoffersen。
- 多重检验：1−(1−α)ⁿ（n=10→40.1%，n=100→99.4%）。
- 情景回放：累计损失 = 1−Π(1+r_t)；峰谷 = 窗口内净值曲线最大回撤
  （损失口径）；Peak/VaR、Peak/ES 无量纲比值。
- reverse stress：所需市场冲击 S* = 阈值/β（β 用 performance.beta 口径），
  在基准 h 日滚动累计收益分布上取经验分位（≤S* 的窗口占比）与
  σ 倍数 S*/σ_roll。
- CBB：块长 q≈√n（向上取整），b 次重抽样；指标置信区间取 bootstrap
  分布的 (α/2, 1−α/2) 分位；MC 标准误 = std(g*)/√b。

## Scope

1. `src/quant_research_engine/risk/`：新增 `backtest_var.py`、`stress.py`、
   `inference.py`；改 `constants.py`（情景库常量、bootstrap 默认）、
   `report.py`（三节扩展）、`__init__.py`（导出新模块）。
2. `tests/test_risk_backtest_var.py`、`test_risk_stress.py`、
   `test_risk_inference.py`；`test_risk_report.py` 增补。
3. docs/agent 08/10/09/05/11 同步。

## Non-Goals

- 不 git commit、不重启 qre-gui.service。
- 不做 R3（markdown 渲染、回测报告集成钩子、GUI 展示区）与 R4 晋升闸。
- 不读 DB；情景库只存日期窗口常量，不提供真实行情数据（回放输入由调用方给）。
- 不做 Basel 三区交通灯、不做 Expected Shortfall 回测（教材本批章节未覆盖）。

## Expected Tests

- HIT 构造手算（已知 returns/VaR → 0/1 序列）。
- 覆盖率 LR 手算小样本（n=100, x=10, p=0.05 等）对 scipy chi2 p 值；
  x=0/x=n 边界不 NaN；违约率恰等于 1−p 时 LR=0。
- 独立性 LR 对手算转移计数；独立合成序列大样本不拒绝、聚集序列拒绝。
- false_positive_probability：1−0.95^10≈0.401263、^100≈0.994079。
- 情景回放手算：已知窗口收益 → 累计损失/峰谷精确值；Peak/VaR 比值；
  相关性崩溃：构造窗口内相关性显著上升的合成数据 → delta 方向正确。
- reverse stress 手算：合成基准滚动分布 → 分位/σ 倍数核对；β≤0 时报错或
  给出不可穿透说明。
- bootstrap：固定 seed；合成已知分布数据 → 95% CI 包含样本统计量；
  MC 标准误 = std/√b 核对；iid 与 cbb 双方法均产出；块长默认 ceil(√n)。
- report：新三节键结构、config 开关（stress/bootstrap 默认关、var_backtest
  默认开）、显式 var_series 覆盖默认 EWMA VaR。
- `uv run pytest tests/ -x -q` 全绿（基线 1532，只增不红）。

## Validation

1. `uv run pytest tests/ -x -q`
2. `scripts/check-progress-docs.sh`
3. `git diff --check`；`git status` 核对变更清单
