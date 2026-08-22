# Review Report

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
