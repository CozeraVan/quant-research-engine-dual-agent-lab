# Review Report

## Task ID

QRE-RISK-PORTFOLIO-007（FRM 风险管理模块 R7：组合层汇总 + risk_report 扩展 + GUI 卡片 + 可选闸扩展）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R7 一一对应**：组合层汇总（risk/portfolio.py：股票腿
  R1–R4 收益序列法、债券/转债腿 DV01/KR01、期权腿组合 Greeks、可选
  DGV-VaR）、risk_report 扩展（可选 portfolio 节 + markdown 渲染）、
  GUI 卡片组（沿用 risk-card 模式，有节才显示）、晋升闸可选判据
  （默认关闭）全覆盖。
- **纪律一致**：portfolio.py 纯函数零 DB；参数集中 constants.py 并回显；
  既有 risk 模块零行为改动（仅 report.py 增加可选节 + __init__ 增列）。
- **向后兼容（专项测试覆盖）**：默认 run 产物零变化（收尾钩子不传衍生品
  键，top-level keys 测试未改动仍绿）；老格式 report（无 portfolio 节、
  老 meta 无 sections）markdown/GUI/闸三处均不炸；闸阈值默认 None 时
  evaluate_gate_risk 返回与 R4 逐键一致（set(risk) 断言）。
- **数值自检**：KR01 按节点加总 = 合并现金流单独跑 key_rate_shifts
  （rel 1e-12），kr01_sum ≈ 曲线口径 DV01（一阶恒等式 rel 1e-4）；
  债券聚合/期权 Greeks 加对手算；DGV-VaR 复用 R6 已验证内核。
- **披露**：DGV 需调用方显式给 spot/vol shock（组合层无标的价格水平）；
  kr01_sum 与 portfolio DV01 口径可不同不强制相等（并列披露）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1724 passed, 4 warnings（基线 1696 + 28 净增，全绿）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006（FRM 风险管理模块 R6：期权计算内核 + DGV-VaR）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R6 表一一对应**：options.py（BSM 无股息/q/离散股息、
  Black's、隐波 brentq、CRR 欧式+美式含 q、树第一层 delta、美式 Greeks
  数值差分、Greeks 全组含 q 版与期货期权版、组合 Greeks 加权）与
  derivatives_var.py（DGV 近似 P&L、正态/CF 分位、VaR 序列对接
  backtest_var_summary 复用 HIT/LR，未新造回测引擎）全覆盖；不做项
  （Heston/波动率曲面/LSM/奇异期权）未触碰。
- **纪律一致**：纯函数零 DB；参数集中 constants.py（IV_BRACKET/
  DEFAULT_TREE_STEPS/GREEK_SHOCK_SIGMA/GREEK_SHOCK_RATE）并全部在
  结果 dict 回显；既有 risk 模块零行为改动（仅 __init__ 增列）。
- **数值验收（CR §4 R6 行全部通过）**：BSM 教材例 d1=0.2001/
  d2=−0.1674/c=8.3069/p=7.9715 + parity 1e-10 自洽；隐波 7.00→25.14%；
  美式 put 教材节点值（A=3.058/B=0.494/C=5.699 行权/欧式 2.838）+
  收敛 20/50/100/500 → 3.082/3.067/3.059/3.055；PDE 恒等式
  （q=0 与 q 版 (r−q)SΔ 形式）1e-10；纯 gamma 组合解析二阶矩
  Var=½Γ²sS⁴ 核对；CF-VaR 对 MC 分位 rel 5%（偏度<0.5 适用域）；
  VaR 序列→backtest_var_summary 集成回测违约率 ≈1% 不拒绝。
- **教材参数溯源**：二叉树收敛例参数（S=29,K=30,r=3%,σ=25%,T=1）
  摘要未载明，已从教材原文 PDF p193 抽取确认（Figure 14.5/14.6
  及收敛段），注释写入测试文件头。
- **自审修正**：Black76 theta 首版符号错误（−r·c 应为 +r·f 结构），
  由有限差分自检测试发现后修正为 θ = r·f − F₀e^{−rT}N′(d1)σ/(2√T)，
  修正后五值全对有限差分（rel 1e-5）。
- **遗留/披露**：CF 在高偏度（纯 gamma χ² 型）下分位失真为已知限制
  （docstring+测试注明，矩核对不受影响）；DGV 的 δS/δσ 独立假设披露；
  CRR 树↔BSM 收敛测试容差 abs 3e-3（O(1/n) 振荡收敛性质）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1696 passed, 4 warnings（基线 1657 + 39 净增，全绿）
tests/test_risk_options.py + tests/test_risk_derivatives_var.py 单独 39/39 绿
scripts/check-progress-docs.sh → 待 docs 同步后运行
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005（FRM 风险管理模块 R5：利率与债券计算内核）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R5 表一一对应**：rates.py（式 16.1–16.5 复利换算、
  PV/FV、spot↔折现因子、书4 Ch9 bootstrap、线性/对数线性插值、
  远期利率连续式与式 10.5、par yield 式 16.7/10.4）与 bonds.py
  （YTM brentq、式 9.2/30-360 应计利息、式 12.6 久期凸性、式 12.1/12.3
  effective、DV01 与 D↔DV01、组合聚合与对冲配比、式 12.4 二阶近似、
  书4 Ch13 KR01、书3 Ch16/17 转债债底与 spread duration）全覆盖；
  不做项（PCA/条款引擎/信用违约/互换期货）未触碰。
- **纪律一致**：纯函数、零 DB、零行情依赖；参数集中 constants.py
  （DEFAULT_DAY_COUNT/CURVE_INTERPOLATION/KEY_RATE_TENORS/
  RATE_SHOCK_BP/YTM_BRACKET）并全部在结果 dict 回显；day count 默认
  actual/actual 符合中国惯例约束；曲线统一连续复利零息利率口径并在
  docstring 披露。既有 risk 模块零行为改动（仅 __init__ 增列）。
- **数值验收（CR §4 R5 行全部通过）**：
  - 书4 Ch9 bootstrap：d = 0.991909/0.980944/0.969406/0.956909
    （实测 1e-6 内精确复现，另加折现回验自洽）；
  - par yield：2.2103%（式 16.7 手算一致）+ 平价债回验 100.0；
  - 平坦曲线连续年金解析解 P/D/C = 8.6394/4.7504/30.862（周网格
    离散逼近 rel<1e-2）；
  - DV01↔D 换算自洽（duration_from_dv01 = effective duration，1e-12）；
  - ΣKR01 = DV01（一阶，rel 3.5e-6 内，rtol 1e-4 自检通过）；
  - +100bp 平行移动二阶近似 vs 直接重定价 rel 偏差 1.9e-5 < 1e-3。
- **顺手修复**：pyproject.toml 补 scipy>=1.11.0 显式依赖（constants.py
  自 R1 起 import scipy 但未声明，CR §3 已点名）。
- **遗留/披露**：KR01 的 Σ=DV01 为一阶恒等式（二阶残差已写进 note 与
  测试容差）；插值域外平坦外推已披露；测试 3 处首版手算/口径错误
  （0.928597→0.928599、年金网格 int、spread duration 对比基准应为
  r+s 水平）已在实现内修正，非源码缺陷。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1657 passed, 4 warnings（基线 1605 + 52 净增，全绿）
tests/test_risk_rates.py + tests/test_risk_bonds.py 单独 52/52 绿
scripts/check-progress-docs.sh → 待 docs 同步后运行
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004（FRM 风险管理模块 R4：晋升全量回测闸加入风险判据）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **改动最小、复用到位**：闸判据挂在唯一收口点
  `refresh_registry.gate_blocks_daily`（refresh_batch.py /
  list_catalog_strategies / refresh_overview 三处调用方零改动自动生效）；
  风险数据复用 R3 既有 `risk_report.load_risk_report` 与
  `runs/<run_id>/risk_report.json`，无新增存储、无 DB 访问。
- **判据语义符合任务书**：ES99 取历史模拟口径（经验日收益，非参数
  假设）阈值 3%（`risk/constants.py::GATE_ES99_MAX`，可调整）；VaR 回测
  取 99% 节覆盖率 Kupiec LR `reject_5pct`（与 ES99 同置信，
  `GATE_VAR_CONFIDENCE`）；主判据（交易≥30 且超额>0）逻辑零改动，
  warning 只影响 `gate_blocks_daily` 与 admin 徽标。unavailable（无
  report/损坏/run 失败）不阻断——专项测试覆盖。
- **force 通道**：warning + forced → 评估照跑、`forced` 透传、
  gate_blocks_daily=False（专项测试）；admin tooltip 注明「force 晋升，
  不阻止日更」。
- **存量兼容**：旧 gate json 无 risk 节 → `gate.get("risk")` 为 None，
  gate_blocks_daily 行为与 R4 前完全一致（test_gui_admin_p3b 既有用例
  未改动、全绿佐证）；admin 仅在 risk.status==='warning' 时追加徽标。
- **字段缺失健壮性**：老格式 report 缺 tail/var_backtest 键时子项记
  None、不触发 warning（evaluate_gate_risk 逐层 `or {}` 取值）。
- **偏差**：无 Required Fix。已知边界：①风险判据取 99% 单置信节
  （95% 节拒绝不触发 warning），与任务书「ES99 + VaR 回测」口径一致；
  ②独立性 LR 不进闸判据（仅报告层展示），因任务书只点名 Kupiec
  覆盖率；③run 失败时 risk=unavailable（此时 gate 已 failed 阻断，
  risk 维度无增量信息）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1605 passed, 4 warnings（2026-08-22，
  QRE-RISK-GATE-004；基线 1599 + 6 净增：test_gui_strategy_create.py
  R4 节 5 新 + test_gui_admin_strat_tab.py 徽标 1 新）
定向：tests/test_gui_strategy_create.py test_gui_admin_strat_tab.py
  test_refresh.py test_gui_admin_p3b.py → 103 passed（2.86s）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

## Nice-to-Have

- 后续可考虑把 95% 节 VaR 回测也纳入判据、或对存量 gate 回填 risk 节；
  均不影响本次正确性，留待用户决策。
