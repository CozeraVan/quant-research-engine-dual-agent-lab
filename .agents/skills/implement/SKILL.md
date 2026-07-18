---
name: implement
description: Single-agent implementation flow that executes the current Implementation Brief and writes the Coding Handoff.
---

# Implement

Use this when the phase is `IMPLEMENTING` (including fix rounds after a self-review with Required Fixes).

Read:

- `AGENTS.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/10_REVIEW_REPORT.md` if fixing Required Fixes
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

- Phase: `SELF_REVIEW`
- Owner: `KIMI_CODE`
