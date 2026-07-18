# Recovery Protocol

Use this file when:

- a session was interrupted,
- terminal closed,
- network failed,
- the user or the agent forgot the current task state,
- several work rounds completed without a self-review,
- git finalization was delayed,
- the normal single-agent sequence was broken.

## Recovery Steps

1. Do not modify code immediately.
2. Read:
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/08_IMPLEMENTATION_BRIEF.md`
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/10_REVIEW_REPORT.md`
3. Run:
   ```bash
   git status
   git diff --name-only HEAD
   git diff HEAD
   git log --oneline -5
   ```
4. Determine:
   - Current Task ID
   - Current Phase
   - Whether code has unreviewed changes
   - Whether self-review has Required Fixes
   - Whether git finalization has happened
5. Output a recovery summary.
6. Wait for user confirmation before editing code or committing.

## Recovery Decision Table

| Observed State | Next Action |
|---|---|
| No brief exists | Write `08_IMPLEMENTATION_BRIEF.md` (Phase: `PLANNING`) |
| Brief exists, no implementation | Implement from brief (Phase: `IMPLEMENTING`) |
| Implementation exists, no review | Inspect diff and write `10_REVIEW_REPORT.md` (Phase: `SELF_REVIEW`) |
| Review has Required Fixes | Fix only Required Fixes (Phase: `IMPLEMENTING`) |
| Review passes, no commit | Run final git checks, propose commit message, wait for user approval (Phase: `AWAITING_GIT_APPROVAL`) |
| Git finalization complete | User acceptance and next request (Phase: `DONE`) |

## Rule

If the state is unclear, prefer stopping after the recovery summary and asking the user, rather than continuing implementation on assumptions. The `docs/agent/` files — not chat history — decide what is true.
