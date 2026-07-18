---
name: plan-brief
description: Single-agent planning flow that converts a user request or Change Request into an Implementation Brief.
---

# Plan Brief

Use this when starting a new non-trivial task and the phase is `PLANNING` (or no brief exists for the requested work).

Read:

- `AGENTS.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- active Change Request if any

Write:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`

The brief must state: Task ID, goal, scope, required behavior, non-goals, expected tests, validation commands, acceptance criteria.

Then update:

- `docs/agent/11_AGENT_STATE.md` (Phase: `PLANNING` → `IMPLEMENTING` once implementation starts)
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`

For large or ambiguous tasks, present the brief/plan to the user for approval before implementing. For clearly directed small tasks, proceed directly.
