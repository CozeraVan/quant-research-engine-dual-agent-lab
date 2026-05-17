# Review Report

## Task ID

TBD

## Written By

CODEX

## Reviewed Implementation

TODO

## Summary

TODO

## Compliance with Implementation Brief

TODO

## Locked Requirements Check

TODO

## Code Quality Issues

TODO

## Potential Bugs / Risks

TODO

## Missing Tests

TODO

## Required Fixes

None yet.

## Recommended Improvements

TODO

## Follow-up Tasks

TODO

## Git Finalization Readiness

| Check | Status | Evidence |
|---|---|---|
| Brief satisfied | TODO | - |
| Required Fixes cleared | TODO | - |
| Tests/checks run | TODO | - |
| Progress docs updated | TODO | - |
| Secrets absent from diff | TODO | - |
| User approval to push | TODO | - |

## Instructions for Claude Code

If Required Fixes are present, Claude Code should:

1. Fix Required Fixes first.
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
