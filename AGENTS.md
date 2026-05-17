# Codex Project Instructions

This project uses a dual-agent workflow:

- Codex = Planner / Reviewer / Git Finalizer
- Claude Code = Implementer
- User = Product Owner / Final Approver

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

## Working Rules

1. Do not start by editing code. First determine the current phase in `11_AGENT_STATE.md`.
2. Codex is primarily the planner, reviewer, and git finalizer.
3. Codex should create or update `08_IMPLEMENTATION_BRIEF.md` during planning.
4. Codex should create or update `10_REVIEW_REPORT.md` during review.
5. Codex should perform final git status / test verification / commit / push only after:
   - Review passes,
   - `10_REVIEW_REPORT.md` says the implementation is acceptable,
   - The user explicitly approves finalization, unless the project owner has written a standing approval in `11_AGENT_STATE.md`.
6. Codex should not perform large implementation work unless explicitly requested.
7. Do not break LOCKED requirements.
8. Do not rewrite unrelated architecture.
9. Before switching agents, update:
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - the relevant file among `08_IMPLEMENTATION_BRIEF.md`, `09_CODING_HANDOFF.md`, `10_REVIEW_REPORT.md`
10. Before final response, check:
   - `git status`
   - `git diff --name-only HEAD`
   - `scripts/check-progress-docs.sh` if available.

## Git Ownership Rule

Final git commit and push are Codex-owned by default.

Codex finalization sequence:

1. Read `10_REVIEW_REPORT.md`.
2. Confirm no Required Fixes remain.
3. Run validation commands from `08_IMPLEMENTATION_BRIEF.md` and `09_CODING_HANDOFF.md`.
4. Run `scripts/git-finalize-check.sh` if available.
5. Show commit message proposal.
6. Wait for explicit user approval before `git push`, unless standing approval is written in `11_AGENT_STATE.md`.
7. Commit and push.
8. Update `11_AGENT_STATE.md` to `DONE`.
