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
