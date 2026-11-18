# Kimi Code Project Instructions

This project uses a single-agent workflow:

- Kimi Code = sole development agent (Planner / Implementer / Self-Reviewer / Git Executor)
- User = Product Owner / Final Approver

The project was migrated from the former dual-agent workflow (Codex planning/review + Claude Code implementation) to single-agent development on 2026-07-18. The migration decision is recorded in `docs/agent/06_DECISION_LOG.md`.

Before modifying code or producing plans, read:

- 文档总索引：`docs/agent/README.md`（按主题查找，不再把全部历史文档列为每次必读）。
- 当前状态：`docs/agent/11_AGENT_STATE.md`、`docs/agent/30_WEEKLY_HANDOFF_2026-11-03.md`。
- 核心合同：`docs/agent/00_PRODUCT_VISION.md`、`02_LOCKED_REQUIREMENTS.md`、`14_LAUNCH_ROADMAP.md`。
- 开发闭环：`docs/agent/04_TASK_HANDOFF.md`、`05_PROGRESS.md`、`08_IMPLEMENTATION_BRIEF.md`、`09_CODING_HANDOFF.md`、`10_REVIEW_REPORT.md`。
- UI 改动另读：`docs/agent/12_UI_STYLE_GUIDE.md`、`23_KLINE_IMPLEMENTATION.md`、`src/quant_research_engine/gui/static/card-class.css`。
- 数据、容量或回测改动另读：`docs/agent/20_DATA_DICTIONARY_DAILY_MINUTE.md`、`24_PERF_METRICS_CONTRACT.md`、`31_RESOURCE_MODEL_2026-11-03.md`、`35_CAPACITY_MODEL_2026-11-03.md`。
- 经典策略队列另读：`docs/agent/34_CLASSIC_CATALOG_PUBLIC_SMOKE_2026-11-03.md`、`36_CLASSIC_FULLSCALE_AUTO_RUNBOOK_2026-11-03.md`。
- 运维、上云或 Windows UI 协作按索引选读；已收官 TV 文档在 `docs/agent/archive/tradingview/`。

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
