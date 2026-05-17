---
name: update-progress
description: Update handoff, progress tracker, decision log, and agent state after project changes.
---

# Update Project Progress

Before finishing a task that changed code, tests, config, architecture, prompts, schemas, docs, or git workflow:

1. Inspect:
   ```bash
   git status
   git diff --name-only HEAD
   git diff HEAD
   ```
2. Update:
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`
3. Update `docs/agent/06_DECISION_LOG.md` if architecture, data, safety, compliance, prompt/schema, backend, sync, deployment, or major design changed.
4. Never mark a task DONE without evidence.
5. Summarize changed task IDs, validations, git status, and next steps.
