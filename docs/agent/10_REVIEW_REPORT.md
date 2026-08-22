# Review Report

## Task ID

QRE-RISK-INTEGRATION-003（FRM 风险管理模块 R3：risk 包集成进回测报告与 GUI 展示）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **集成点最小侵入**：run 收尾钩子完全复刻 finalize_smoke /
  finalize_promotion_gate 的 try/except 兜底模式
  （`gui/engine.py:354-361`），钩子异常不影响 run 状态（专项测试
  `TestEngineHookWiring` 覆盖：钩子抛 RuntimeError 后 status.json 仍为
  completed）。回测引擎本体零改动；risk 包保持可独立 import
  （`render_risk_markdown` 在 risk/report.py，不 import 任何 GUI 模块）。
- **收益口径最小加工**：组合级 `equity_curve.csv` 的 `daily_return` 列
  直取（引擎组合口径）；per-symbol 目录文件按列头排除（含 symbol 列）；
  缺 daily_return 退化 `total_equity.pct_change()`；现状产物无
  `benchmark_close` 列 → benchmark=None，report 基准相关节自动 null，
  markdown 如实显示「无基准收益序列：β/Treynor/IR/Jensen's α 未计算」。
- **幂等与原子写**：risk_report.json tmp+os.replace 原子写；summary.md
  追加「## 风险分析」节前先移除既有同名副（到下一个同级标题），
  二次 finalize 不重复（专项测试覆盖）；无 summary.md 时退化写
  runs/<run_id>/risk_report.md。
- **按需 job**：复用 daily_jobs.start_script_job，
  lock_key=risk-report:<run_id>（同 run 409）；in-process runner 不开
  subprocess；bootstrap 仅在此开启（b=1000 默认，异步可接受）。GET
  轮询端点校验 job.pipeline 前缀防跨 run 串读。
- **#4 策略级 badge 决定不加**（CR 允许）：admin 策略状态表数据源是
  refresh_overview（outputs/refresh 产物，非 GUI run），其产物树没有
  risk_report.json；要显示 ES 需对 refresh 产物额外跑风险分析，属于
  refresh 管线改动，超出 R3「别硬塞」边界。已在 08/09 记录理由。
- **E2E 数值 sanity**（mr01a，5 股 × 2024-2025，vectorized，真实 DB）：
  n=484；99% VaR 参数正态 1.50% / 历史模拟 1.79%，ES 1.72% / 2.19%
  （日损失口径，量级合理）；JB=629.81 p<0.0001 拒绝正态（超额峰度
  5.35，A 股典型）；VaR 回测 95% 违约 19/期望 24.15（covLR p=0.2648）、
  99% 7/4.83（p=0.3524），独立性 p=0.2244/0.6743 → 均不拒绝；
  Sharpe 0.02 / Sortino 0.03（该区间近 flat，与权益曲线一致）；
  四情景中 2024 小微盘窗口覆盖（36 天，累计损失 -6.20% 即盈利，
  峰谷 5.19%），其余三窗口如实标「样本不覆盖」。
  已知现象（R2 口径，非 R3 引入）：该策略长时段空仓 → EWMA σ≈0 →
  EWMA VaR≈0 且 Peak/VaR 比值失真（-2532.15）；属如实输出，
  口径改进留 R4/后续。
- **偏差**：无 Required Fix。GARCH 对该近 flat 序列 α+β=1.00 非平稳
  （arch ConvergenceWarning，report 如实 stationary=False、长期波动
  显示「—」）——渲染层已正确处理 None。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1599 passed, 4 warnings（2026-08-22，
  QRE-RISK-INTEGRATION-003；基线 1578 + 21 净增：test_gui_risk_report.py
  17 新 + test_risk_report.py TestRenderMarkdown 4 新）
首跑 FAILED tests/test_gui_factor_wizard.py::test_job_lock_conflict
  → 全量复跑 1599 全绿（已知环境敏感 flake，任务书已列）
scripts/check-progress-docs.sh → passed
git diff --check → clean
真实 E2E：run 20260822T114522831346（mr01a 5股×2024-2025）completed；
  runs/<run_id>/risk_report.json 生成（meta.sections stress=True
  bootstrap=False）；outputs/gui-run/summary.md 追加「## 风险分析」节，
  既有结构保留；关键数字见 Findings
```
