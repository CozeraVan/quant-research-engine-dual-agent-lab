---
name: codex-plan-brief
description: Codex planner flow that converts a user request or Change Request into an Implementation Brief for Claude Code.
---

# Codex Plan Brief

Use this when Codex is the current owner and phase is `CODEX_PLANNING`.

Do not implement code.

Read:

- `AGENTS.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- active Change Request if any

Write:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`

Then update:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`

Next state after the brief is ready:

- Phase: `WAITING_USER_APPROVAL`
- Owner: `USER`
