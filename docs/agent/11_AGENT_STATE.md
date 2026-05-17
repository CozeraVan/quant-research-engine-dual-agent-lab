# Agent State

This file is the source of truth for dual-agent workflow recovery.

## Current Task ID

NONE

## Current Phase

Allowed values:

- IDEA_INTAKE
- CODEX_PLANNING
- WAITING_USER_APPROVAL
- CLAUDE_IMPLEMENTING
- CODEX_REVIEWING
- CLAUDE_FIXING
- USER_ACCEPTANCE
- CODEX_GIT_FINALIZING
- DONE
- BLOCKED

Current:

IDEA_INTAKE

## Current Owner

Allowed values:

- USER
- CODEX
- CLAUDE_CODE

Current:

USER

## Last Completed Step

Project workflow initialized.

## Next Required Step

User should discuss project goals and architecture with Codex.

## Active Change Request

None

## Active Implementation Brief

`docs/agent/08_IMPLEMENTATION_BRIEF.md`

## Active Coding Handoff

`docs/agent/09_CODING_HANDOFF.md`

## Active Review Report

`docs/agent/10_REVIEW_REPORT.md`

## Git State

- Current branch: TODO
- Remote: TODO
- Last checkpoint commit: TODO
- Last implementation commit: TODO
- Last review commit: TODO
- Last pushed commit: TODO

## Standing Approval

Default:

- Codex may prepare commit and push plan.
- Codex must ask user before `git push`.

To allow Codex to push automatically for this project, user must explicitly write a standing approval here.

Standing approval:

NONE

## Recovery Instruction

If unsure where to continue:

1. Read this file first.
2. Read:
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/08_IMPLEMENTATION_BRIEF.md`
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/10_REVIEW_REPORT.md`
3. Run:
   ```bash
   git status
   git diff
   git log --oneline -5
   ```
4. Determine current phase before modifying code.
5. If current owner is not the active agent, do not proceed.

## Manual Phase Transition Rules

### User -> Codex Planning

When the user gives a new idea:

- Phase: `CODEX_PLANNING`
- Owner: `CODEX`

### Codex Planning -> User Approval

After Codex writes Implementation Brief:

- Phase: `WAITING_USER_APPROVAL`
- Owner: `USER`

### User Approval -> Claude Implementation

After user approves the brief:

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`

### Claude Implementation -> Codex Review

After Claude Code finishes implementation:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`

### Codex Review -> Claude Fixing

If Required Fixes exist:

- Phase: `CLAUDE_FIXING`
- Owner: `CLAUDE_CODE`

### Codex Review -> User Acceptance

If review passes:

- Phase: `USER_ACCEPTANCE`
- Owner: `USER`

### User Acceptance -> Codex Git Finalizing

If user approves commit/push:

- Phase: `CODEX_GIT_FINALIZING`
- Owner: `CODEX`

### Codex Git Finalizing -> Done

After successful commit/push:

- Phase: `DONE`
- Owner: `USER`
