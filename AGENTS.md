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
