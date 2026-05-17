# Claude Code Project Instructions

This project uses a dual-agent workflow:

- Codex = Planner / Reviewer / Git Finalizer
- Claude Code = Implementer
- User = Product Owner / Final Approver

Before modifying code, read:

@docs/agent/00_PRODUCT_VISION.md
@docs/agent/01_CURRENT_STATUS.md
@docs/agent/02_LOCKED_REQUIREMENTS.md
@docs/agent/03_ROADMAP.md
@docs/agent/04_TASK_HANDOFF.md
@docs/agent/05_PROGRESS.md
@docs/agent/06_DECISION_LOG.md
@docs/agent/07_RECOVERY_PROTOCOL.md
@docs/agent/08_IMPLEMENTATION_BRIEF.md
@docs/agent/09_CODING_HANDOFF.md
@docs/agent/10_REVIEW_REPORT.md
@docs/agent/11_AGENT_STATE.md

## Working Rules

1. Do not modify code before reading the project docs listed above.
2. Before doing work, read `docs/agent/11_AGENT_STATE.md` and determine whether the current owner is Claude Code.
3. Claude Code is primarily the implementer. Do not invent architecture beyond the Implementation Brief.
4. New ideas, feature changes, deletions, and refactors must first become a Change Request.
5. Do not break LOCKED requirements.
6. Do not rewrite unrelated architecture.
7. Before editing, explain affected files, forbidden files, risks, and validation.
8. After implementation, update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`
9. If architecture, data model, prompt/schema, safety, compliance, backend, sync, deployment, or major design changed, update:
   - `docs/agent/06_DECISION_LOG.md`
10. Claude Code should not perform final git commit/push unless the user explicitly overrides the dual-agent workflow.
11. Final git commit and push are Codex-owned steps after review passes and the user approves.
12. If the previous session was interrupted, follow `docs/agent/07_RECOVERY_PROTOCOL.md` first.

## Dual-Agent Phase Rules

- If phase is `CODEX_PLANNING`, Claude Code should not implement yet.
- If phase is `CLAUDE_IMPLEMENTING`, Claude Code should implement strictly from `08_IMPLEMENTATION_BRIEF.md`.
- If phase is `CODEX_REVIEWING`, Claude Code should wait for Codex review.
- If phase is `CLAUDE_FIXING`, Claude Code should only fix Required Fixes from `10_REVIEW_REPORT.md`.
- If phase is `CODEX_GIT_FINALIZING`, Claude Code should not commit or push unless explicitly instructed.
