# Review Report

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
