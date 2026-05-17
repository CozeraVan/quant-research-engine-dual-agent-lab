---
name: claude-implement
description: Claude Code implementation flow that executes the current Implementation Brief and writes Coding Handoff.
---

# Claude Implement

Use this when Claude Code is the current owner and phase is `CLAUDE_IMPLEMENTING` or `CLAUDE_FIXING`.

Read:

- `CLAUDE.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/10_REVIEW_REPORT.md` if phase is `CLAUDE_FIXING`
- `docs/agent/11_AGENT_STATE.md`

Rules:

1. Implement only what the brief requires.
2. If fixing, fix only Required Fixes.
3. Avoid unrelated refactors.
4. Run available validation commands.
5. Update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`

Next state after implementation:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
