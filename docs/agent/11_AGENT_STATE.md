# Agent State

This file is the source of truth for dual-agent workflow recovery.

## Current Task ID

QRE-REPORT-DOCS-JSON-CLI-001

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

CLAUDE_IMPLEMENTING

## Current Owner

Allowed values:

- USER
- CODEX
- CLAUDE_CODE

Current:

CLAUDE_CODE

## Last Completed Step

Codex created local checkpoint `faa95e2 feat: add report files json output` and prepared the next implementation brief for README report CLI JSON documentation.

## Next Required Step

Claude Code should implement `QRE-REPORT-DOCS-JSON-CLI-001` strictly from `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Active Change Request

User request from 2026-05-18:

- run One-Shot Review-Finalize-Next,
- if review passes, validate and commit locally without push,
- prepare and commit the next Claude Code implementation handoff.

## Active Implementation Brief

`docs/agent/08_IMPLEMENTATION_BRIEF.md`

## Active Coding Handoff

`docs/agent/09_CODING_HANDOFF.md`

## Active Review Report

`docs/agent/10_REVIEW_REPORT.md`

## Active Agent Board

`docs/agent/12_AGENT_BOARD.md`

## Git State

- Current branch: `master`
- Remote: none shown by prior `git remote -v`
- Last checkpoint commit: `7657cd1 checkpoint: original quant-research-engine before dual-agent pilot`
- Last workflow commit: `77fec02 chore: initialize dual-agent workflow`
- Last docs migration commit: `2565e13 checkpoint: dual-agent docs migrated and legacy docs archived`
- Last accepted implementation commit: `28e6f25 feat: add failed-order diagnostics to portfolio reports`
- Last local implementation commits:
  - `001177f test: validate failed-order report artifacts`
  - `e568823 feat: add strict report-files matching`
  - `3f7d623 feat: add report audit json output`
  - `faa95e2 feat: add report files json output`
- Last pushed commit: no remote configured
- Current planning docs for `QRE-REPORT-DOCS-JSON-CLI-001` are uncommitted.

## Standing Approval

Default:

- Codex may create local git checkpoints after review passes.
- Codex must not push unless explicit user approval or standing approval exists.

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
   - `docs/agent/12_AGENT_BOARD.md`
3. Run:
   ```bash
   git status
   git diff
   git log --oneline -5
   ```
4. Determine current phase before modifying code.
5. If current owner is not the active agent, do not proceed.

## Short Prompt Commands

### For Claude Code

```text
请读取 11 和 12，执行当前 Claude Code 任务。
```

### For Codex

```text
请读取 11 和 12，执行 One-Shot Review-Finalize-Next。
```

## One-Shot Review Routing State Transitions

Use this compressed routing when:

- Current Phase = `CODEX_REVIEWING`
- Current Owner = `CODEX`
- the user asks Codex to execute One-Shot Review-Finalize-Next

### Fail Path

If Codex review fails:

- Codex must update `10_REVIEW_REPORT.md` with `Review Outcome = FAIL`.
- Codex must write Required Fixes.
- Codex must update `12_AGENT_BOARD.md` with a concise fix request for Claude Code.
- Codex must not commit.
- Codex must not push.
- Next Phase: `CLAUDE_FIXING`
- Next Owner: `CLAUDE_CODE`

### Pass Path

If Codex review passes:

- Codex must update `10_REVIEW_REPORT.md` with `Review Outcome = PASS`.
- Codex must run required validation.
- Codex must update progress and handoff docs.
- Codex must create a local git commit for the accepted implementation.
- Codex must not push unless explicit approval or standing approval exists.
- Codex must prepare the next small, low-risk, testable task.
- Codex must update `08_IMPLEMENTATION_BRIEF.md`.
- Codex must reset or update `09_CODING_HANDOFF.md`.
- Codex must update `12_AGENT_BOARD.md` for Claude Code.
- Codex should create a second local git commit for the next planning and handoff docs whenever possible.
- Next Phase: `CLAUDE_IMPLEMENTING`
- Next Owner: `CLAUDE_CODE`
