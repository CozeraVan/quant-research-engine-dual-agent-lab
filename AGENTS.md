# Kimi Code Project Instructions

This project uses a single-agent workflow:

- Kimi Code = sole development agent (Planner / Implementer / Self-Reviewer / Git Executor)
- User = Product Owner / Final Approver

The project was migrated from the former dual-agent workflow (Codex planning/review + Claude Code implementation) to single-agent development on 2026-07-18. The migration decision is recorded in `docs/agent/06_DECISION_LOG.md`.

Before modifying code or producing plans, read:

- `docs/agent/00_PRODUCT_VISION.md`
- `docs/agent/01_CURRENT_STATUS.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/06_DECISION_LOG.md`
- `docs/agent/07_RECOVERY_PROTOCOL.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/10_REVIEW_REPORT.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_UI_STYLE_GUIDE.md`（UI 设计语言规范：后续页面开发必须遵守，改动需用户批准）
- `src/quant_research_engine/gui/static/card-class.css`（**小数据卡唯一样式权威**：白底紫框 + 中性紫/盈亏红绿 + flex 自适应；改这类卡只改这个文件）
- `docs/agent/13_UI_PERF_NOTES.md`（UI 性能评估与优化方案）
- `docs/agent/14_LAUNCH_ROADMAP.md`（上线路线图与工作手册：现状/ECS 架构/迁移阶段/踩坑/工作流/挂起任务）
- `docs/agent/15_SAAS_SYSTEMS_DESIGN.md`（SaaS 系统设计：用户/Job/结果/管理四系统与分阶段 TODO）
- `docs/agent/16_ECS_DEPLOYMENT.md`（ECS 部署单一权威文档：实例/访问/现状/待办/运维速查）
- `docs/agent/18_AUTH_MEMBERSHIP_DESIGN.md`（Authing 身份层 + Flask 会员体系设计：登录链路/数据模型/迁移/阶段 TODO）
- `docs/agent/19_MONETIZATION_MATRIX.md`（可付费项目矩阵：11 项付费点映射 + 内测期两层开放原则，会员/管理台建设权威依据）
- `docs/agent/20_DATA_DICTIONARY_DAILY_MINUTE.md`（行情数据字典：日线/分钟线表结构、单位口径、TimescaleDB 规范、PIT 硬规则）
- `docs/agent/21_FACTOR_LIBRARY_PLAN.md`（Tushare 202 因子本地复现立项方案：表设计/P0-P8 批次/验收/风险）
- `docs/agent/23_KLINE_IMPLEMENTATION.md`（当前 K 线实现、数据合同、重播、因子呈现、主题与游戏交接）
- `docs/agent/TV_FEEDBACK_2026-10-28.md`（TradingView 化本轮反馈：对照逆向 agent 报告的四功能完成度/未完成原因/难点/待回复问题；下一轮 TV 化的输入）
- `docs/agent/TV_ROUND2_SUMMARY_2026-10-29.md`（**给逆向侧的下一轮输入**：本轮成果汇总 + 4 个待逆向侧回答的问题 + 可自行复跑的复核命令）
- `docs/agent/TV_ROUND2_ANSWER_2026-10-29.md`（**我方逐项回传**：§3 判据原始输出 + T1–T6 验收细节；**派下一轮前必读 §5bis 收官状态表与 5 条新发现**）
- `docs/agent/TV_ROUND3_ANSWER_2026-10-29.md`（**ROUND3 回传**：R3-1 零基线 / R3-2 三项补验自动化+2 个真 bug / R3-4 移除 LWC 省 214KiB / R3-5 双列名收敛 / R3-3 前提纠正；下一轮建议见 §8）
- `docs/agent/TV_ROUND4_ANSWER_2026-10-30.md`（**ROUND4 回传**：R4-1 四类「单测绿生产炸」清扫 / R4-2 判据环境段+一行化入口 / R4-3 模板语法守卫（含事故红灯复现）/ R4-4 旧系退场事件触发制+周扫首扫 / R4-5 用户选 A 维持原状）
- `docs/agent/TV_FINAL_REPORT_2026-10-30.md`（**TV 化收官报告**：最终记分卡（K线95/作图90/指标95/回放95）/ 8 条有意偏离清单 / 判据与守卫测试资产清单 / 稳态机制 / 三个收官数字 / 三条长期纪律）
- `docs/agent/TV_ROUND5_ANSWER_2026-10-30.md`（**ROUND5 收官轮回传**：probe 落盘 / AGENTS.md 两条纪律节 / 周扫 timer + LEGACY_RETENTION_DAYS（默认 90，待用户确认）/ 收官报告与三个数字）
- `docs/agent/24_PERF_METRICS_CONTRACT.md`（持股周期与 α/β/IR/Sharpe 口径合同：公式/常量/基准选择/前端后端分工/防漂移纪律；用这些指标前必读）
- `docs/agent/24_KLINE_LWC_FROZEN.md`（LWC 引擎试点**已整体移除**（R3-4，省 ~214KiB）：删除清单/收益/决策记录/重新引入条件；版本锁定信息指向 git 历史）

## Long-Term Memory Rule

The markdown files under `docs/agent/` are the project's only authoritative long-term memory. Chat/CLI conversation history is not a source of truth.

- Every meaningful change (code, tests, config, architecture, workflow) must be recorded in the relevant `docs/agent/` files in the same work session.
- If conversation and docs disagree, the docs win (see R-AGENT-003 in `02_LOCKED_REQUIREMENTS.md`).
- A future session must be able to reconstruct the full project state from these files alone.

## Working Rules

1. Do not start by editing code. First determine the current phase in `docs/agent/11_AGENT_STATE.md`.
2. Kimi Code owns the full development cycle: planning (`08_IMPLEMENTATION_BRIEF.md`), implementation, self-review (`10_REVIEW_REPORT.md`), and git finalization.
3. New ideas, feature changes, deletions, and refactors should first become a Change Request under `docs/agent/change_requests/` unless the user directs the work explicitly.
4. Write or update `08_IMPLEMENTATION_BRIEF.md` before non-trivial implementation.
5. Write or update `10_REVIEW_REPORT.md` after implementation, before git finalization.
6. Do not break LOCKED requirements in `02_LOCKED_REQUIREMENTS.md`.
7. Do not rewrite unrelated architecture.
8. Keep changes minimal and verifiable; every change needs a validation path.
9. When finishing an implementation slice, update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`
10. If architecture, data model, schema, safety, or major design changed, also update `docs/agent/06_DECISION_LOG.md`.
11. Before final response, check:
    - `git status`
    - `git diff --name-only HEAD`
    - `scripts/check-progress-docs.sh` if available.
12. Deployment-before-review (user standing instruction, 2026-10-26): after any code/UI change, back up the affected production files and deploy directly to ECS without asking for deployment approval. Do not commit or push until the user manually accepts the deployed result. If rejected, restore the previous production version immediately. Documentation-only changes need no ECS synchronization.
13. UI notes (user standing instruction, 2026-10-26): new pages and UI changes must not introduce gray small-font note text in any form. Put necessary explanations into the existing `tip-trigger` + `data-tip` + `LabUI.helpTips` interaction; do not add `.opt`, muted/faint helper paragraphs, or small gray inline notes.
14. Admin synchronization (user standing instruction, 2026-10-26): every permission/quota change must also be visible in the 9090 admin console with its real runtime values and relevant counters before commit/push. Admin presentation must use the same policy source as enforcement; never leave runtime permissions and console display out of sync.

## Silent-Failure Discipline（TV 化 R3/R4 两个真 bug 后新增，每次交互必须执行）

R3-2 修掉的两个 bug 都是「单测全绿、生产炸」：`replay.js` 的 `selected: undefined`
让 K 线重播每帧 seek 抛一次 pageerror（错误在 rAF 回调里，不影响渲染，肉眼与单测
都抓不到）；`const` TDZ 让画线自上线起从不在页面加载时恢复（同会话读回正常，
只有真实浏览器冷启动暴露）。四条纪律由此来，**由测试机器强制**：

1. **静默 catch 必须带理由注释**（同行或上一行）。新写 `catch (e) {}` 无注释
   视为未完成。强制测试：`tests/test_no_silent_failure_patterns.py::
   test_every_silent_catch_has_a_reason_comment`。
   合理的吞只有「环境缺失」语义（localStorage 被禁 / JSON 损坏 / canvas 不可用）；
   兜底吞 ReferenceError/TypeError 一律按 bug 修。
2. **条件键：缺就不写键**（新代码默认风格）。判定存量「键在值为 undefined」
   用**消费方语义**：该键的消费方是否**不解引用就取属性**。
   炸例 `legend.selected`（`LegendModel.isSelected()` 无条件
   `selected.hasOwnProperty(name)`）；不炸例 series 级 `markLine: undefined`
   （ECharts 走无配置分支，probe：`.tmp/perf-browser/probe_markline_undef.py`）。
   **判定标准宽了，写作标准不放宽**；实测不炸的不改，避免无 bug 的 churn。
3. **模块级 `const/let` 不得前向引用后声明的绑定**（TDZ）。初始化器要用的键
   必须声明在前面。强制测试：`test_no_module_level_tdz_forward_reference`。
4. **证据位置必须真实存在**：回传/文档/CR 引用的脚本、截图、输出文件，
   **落盘后才许引用**。`.tmp/` 是 scratch，但被引用的 scratch 就是证据，
   证据不许消失（TV_ROUND4 引用过一个不存在的 probe，R5-4 才补档）。

## TV Acceptance Checklist（TV 化相关改动的提交前验收）

凡改 **K 线 / 因子 pane / 画线 / 重播** 相关代码，提交前跑一次全绿：

```bash
.tmp/perf-browser/tv_check_all.sh
```

覆盖：symbol 静态图判据（含 pane 几何环境段）/ 回放键盘往返 / 画线交互
（含页面重启恢复）/ game.html 判据 / D 类热路径 pageerrors===0 /
B 类冷启动全持久化键恢复。另跑 `uv run pytest tests/test_no_silent_failure_patterns.py
tests/test_template_inline_js_syntax.py -q`（四类模式守卫 + 模板 inline JS 语法守卫）。

模板改动后必须 `node --check` 所有 inline script（先替换 Jinja
`{{ }}`→`null`、`{% %}`→空）——曾有人删注释删穿函数体，pytest 报错离根因极远。

## Data Mutation Discipline（2026-10-28 数据事故后新增，每次交互必须执行）

1. **任何生产表 UPDATE/DELETE，执行前必须跑与 WHERE 完全相同的 `SELECT count(*)`，
   并与已知量级对账；差一个数量级立即中止。** 事故记录见
   `docs/agent/change_requests/CR-2026-10-28_data_incident_low_overwrite.md`
   （`low < LEAST(open,close)` 漏掉 `0.2*close` 守卫，1329 万行被误改）。
2. **数据修复一律先影子表 + 审计表 + 人工换名**，参考 `quant_ts/rebuild_daily_raw.py`，
   不直接 UPDATE 生产表。
3. **备份范围必须覆盖改动范围**；只备份准备改的那几行，却跑了全市场条件的 UPDATE，
   等于没有备份。
4. 从分析到落地的 SQL 条件要逐字核对，每个守卫都必须在最终语句里出现。

## Git Ownership Rule

Kimi Code executes git finalization, but only after all of the following:

1. `10_REVIEW_REPORT.md` says the implementation is acceptable (no Required Fixes).
2. Validation commands from `08_IMPLEMENTATION_BRIEF.md` and `09_CODING_HANDOFF.md` have run.
3. `scripts/git-finalize-check.sh` passes if available.
4. The proposed commit message has been shown to the user.
5. The user has explicitly approved the commit, unless standing approval is written in `11_AGENT_STATE.md`.

Finalization sequence:

1. Run the checks above.
2. Show commit message proposal.
3. Wait for explicit user approval.
4. Commit. Push only if a remote exists and the user asked for it.
5. Update `11_AGENT_STATE.md` phase to `DONE`.
