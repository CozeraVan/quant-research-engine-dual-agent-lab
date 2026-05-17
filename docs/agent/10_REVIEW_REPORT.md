# Review Report

## Task ID

QRE-PORTFOLIO-FAILED-ORDER-DIAGNOSTICS-001

## Written By

CODEX

## Reviewed Implementation

No implementation yet. This task is waiting for user approval and Claude Code implementation.

## Summary

Not reviewed.

## Compliance with Implementation Brief

Not applicable yet.

## Locked Requirements Check

Not applicable yet.

## Code Quality Issues

Not reviewed.

## Potential Bugs / Risks

Not reviewed.

## Missing Tests

Not reviewed.

## Required Fixes

Not applicable until implementation exists.

## Recommended Improvements

None yet.

## Follow-up Tasks

- Real index benchmark wiring after table/schema confirmation.
- Real suspension/ST/risk-warning metadata wiring after source confirmation.
- Evaluation grouping/regime/benchmark/random-baseline extensions.

## Git Finalization Readiness

| Check | Status | Evidence |
|---|---|---|
| Brief satisfied | TODO | Implementation not started |
| Required Fixes cleared | TODO | No review yet |
| Tests/checks run | TODO | No implementation yet |
| Progress docs updated | TODO | To be updated by implementer/reviewer |
| Secrets absent from diff | TODO | To be checked during review |
| User approval to push | TODO | No finalization approval |

## Instructions for Claude Code

If the user approves the brief, Claude Code should:

1. Implement only the approved failed-order diagnostics task.
2. Avoid unrelated rewrites.
3. Update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`

## Instructions for Codex Git Finalization

If there are no Required Fixes and the user approves finalization, Codex should:

1. Run `scripts/git-finalize-check.sh`.
2. Propose a commit message.
3. Run:
   ```bash
   git status
   git add -A
   git commit -m "..."
   git push
   ```
4. Update:
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/04_TASK_HANDOFF.md`

## Next Agent State After Review

If Required Fixes exist:

- Phase: `CLAUDE_FIXING`
- Owner: `CLAUDE_CODE`

If review passes:

- Phase: `USER_ACCEPTANCE`
- Owner: `USER`

If user approves git finalization:

- Phase: `CODEX_GIT_FINALIZING`
- Owner: `CODEX`
