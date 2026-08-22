# Implementation Brief

## Task ID

QRE-RISK-INTEGRATION-003（FRM 风险管理模块 R3：risk 包集成进回测报告与 GUI 展示）

## Created By

KIMI_CODE（用户 2026-08-22 直接指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-21_frm_risk_module.md` R3 阶段；R1 = commit 96db59d、
R2 = commit f52c0f4 已完成，risk 包就绪）

## Intended Implementer

KIMI_CODE

## Goal

把 risk 包接进回测生命周期与 GUI，四处集成：

1. **run 收尾自动生成风险分析**：`gui/engine.py::_execute_and_finalize`
   终态后新增钩子（仿 finalize_smoke/finalize_promotion_gate 的
   try/except 兜底模式，绝不影响 run 本身）。新模块
   `gui/risk_report.py`：
   - `extract_strategy_returns(record)`：从 run 产物定位组合级
     `equity_curve.csv`（排除 per-symbol 目录下的单标的文件；优先含
     `daily_return` 列的组合级文件，退化为 `total_equity.pct_change()`）；
     若含 `benchmark_close` 列则一并取基准逐日收益（现状产物无此列 →
     benchmark=None，report 基准相关节自动为 null）。
   - `finalize_risk_report(record)`：仅 completed run；调
     `risk.report.build_risk_report`（var_backtest 默认开、stress 开、
     bootstrap 关——太慢，留按需）；JSON 原子写
     `outputs/gui-console/runs/<run_id>/risk_report.json`；markdown 节
     （`render_risk_markdown`）追加到产物 `summary.md`（「## 风险分析」，
     若已存在该节则先移除旧节再追加，幂等）；无 summary.md 时写
     `runs/<run_id>/risk_report.md`。
2. **markdown 渲染**：`risk/report.py` 加
   `render_risk_markdown(report_dict) -> str`——汉化、指标两位小数、
   分区：分布与尾部 / VaR 回测 / 波动率 / 压力测试 / 绩效；error 节
   如实显示「数据不足」。
3. **GUI 展示**：`run_detail.html` 新增「风险分析」区——
   - 有 risk_report.json：卡片式渲染（VaR/ES 三口径 95/99、JB 检验结论、
     VaR 回测违约数与 LR 结论、EWMA/GARCH 当前波动率与 regime、四情景
     压力结果表、绩效五指标）。app.py run_detail 路由读取 JSON 传模板。
   - 无（老 run）：显示「未生成」+「生成风险分析」按钮 →
     POST `/api/runs/<run_id>/risk-report`（异步 job 复用 daily_jobs
     start_script_job，lock_key=`risk-report:<run_id>`，in-process
     runner，bootstrap=开）→ 返回 job_id；GET
     `/api/runs/<run_id>/risk-report/job/<job_id>` 轮询；完成后前端刷新。
     404（run 不存在）/409（同 run 已有 job 在跑）/400（run 未完成）。
4. **策略级汇总（可选）**：admin.html 策略列表若无合适位置则不加
   （CR 允许「别硬塞」）——落地时调查后决定并记录理由。

## Semantics

- 收益口径：组合级 `daily_return` 列（引擎组合口径，最小加工）；
  trade_date → DatetimeIndex（stress 情景窗口按日期切片需要）。
- stress 开：四情景库默认；无 benchmark → 无相关性崩溃/基准对照，如实标注。
- bootstrap 仅在按需 job 开启（b=默认 1000，CBB 分钟级可接受于异步）。
- 钩子失败只吞掉（与 smoke/promotion_gate 一致），run 状态不受影响。

## Scope

1. `src/quant_research_engine/risk/report.py`：+ `render_risk_markdown`。
2. `src/quant_research_engine/gui/risk_report.py`（新）：收益提取、
   finalize 钩子、按需 job 启动。
3. `src/quant_research_engine/gui/engine.py`：收尾钩子（try/except 兜底）。
4. `src/quant_research_engine/gui/app.py`：run_detail 传 risk + 两个端点。
5. `src/quant_research_engine/gui/templates/run_detail.html`：风险分析区。
6. `tests/test_risk_report.py` 增补；新 `tests/test_gui_risk_report.py`；
   `tests/test_gui_app.py` 增补端点/模板用例。
7. docs/agent 08/10/09/05/11 同步。

## Non-Goals

- 不 git commit、不重启 qre-gui.service。
- 不做 R4 晋升闸风险判据（单独 CR 审批）。
- 不改回测引擎本体；risk 包保持可独立 import（render 不依赖 GUI）。
- admin.html 策略列表 badge 仅在确有合适位置时加，否则记录理由跳过。

## Expected Tests

- render_risk_markdown：分区齐全（分布与尾部/VaR 回测/波动率/压力/绩效）、
  两位小数、error 节降级为「数据不足」文本、无 stress/bootstrap 键时不渲染对应区。
- extract_strategy_returns：组合级优先（含 daily_return）、per-symbol 目录
  文件被排除、缺 daily_return 时 pct_change 退化、benchmark_close 缺失 → None。
- finalize 钩子：tmp_path 假 run 产物全链路（JSON 落盘 + summary.md 追加 +
  幂等重跑不重复节）；failed run 跳过；无 equity_curve 时不产出不抛错。
- 端点：POST 200（job 启动，runner mock）/404/400/409；GET 轮询 200/404；
  run_detail 模板含/不含 risk 区两种渲染。
- `uv run pytest tests/ -x -q` 全绿（基线 1578，只增不红）。

## Validation

1. `uv run pytest tests/ -x -q`
2. 真实 E2E：catalog 策略小样本真实 run → risk_report.json + summary.md
   风险节，数值 sane（VaR 量级、LR p 值）贴 10_REVIEW_REPORT
3. `scripts/check-progress-docs.sh`
4. `git diff --check`；`git status` 核对变更清单
