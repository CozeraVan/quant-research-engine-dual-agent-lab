# Task Handoff

## Current Task

Standardize failed-order report CSV schema and audit validation.

## Task ID

QRE-REPORT-AUDIT-FAILED-ORDERS-SCHEMA-001

## Current Status

Approved for Claude Code implementation by user request after local checkpoint `28e6f25`.

## Current Owner

CLAUDE_CODE

## Completed

- Finalized previous accepted task locally:
  - `28e6f25 feat: add failed-order diagnostics to portfolio reports`
- Did not push.
- Selected next low-risk reporting robustness task from roadmap/progress context.
- Wrote new implementation brief:
  - `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- Prepared Claude Code handoff board:
  - `docs/agent/12_AGENT_BOARD.md`

## In Progress

Claude Code should implement:

- `QRE-REPORT-AUDIT-FAILED-ORDERS-SCHEMA-001`

Implementation source of truth:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`

## Modified Files For Next Planning Step

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation

Pre-checkpoint validation for previous accepted task:

- `uv run pytest -q` -> `162 passed in 2.29s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

Next task validation requirements are in `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Known Risks

- Do not broaden the task into report manifest redesign.
- Do not change portfolio execution semantics.
- Keep failed-order CSV required columns minimal so older report artifacts are not broken unnecessarily.

## Next Suggested Step

Claude Code implements strictly from `docs/agent/08_IMPLEMENTATION_BRIEF.md`, then updates `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and `docs/agent/12_AGENT_BOARD.md` before handing back to Codex review.
