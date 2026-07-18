---
name: git-finalize
description: Final git verification, commit, and push flow. Executed by the single agent after user approval.
---

# Git Finalize

Executed by Kimi Code (single agent).

Use only when:

- Phase is `AWAITING_GIT_APPROVAL`
- Self-review has passed (`10_REVIEW_REPORT.md` has no Required Fixes)
- The user has explicitly approved the commit (or standing approval exists in `11_AGENT_STATE.md`)

Required checks:

```bash
git status
git diff --name-only HEAD
scripts/check-progress-docs.sh
scripts/git-finalize-check.sh
```

Then:

1. Show the proposed commit message (usually already presented at self-review).
2. Confirm no secrets are included.
3. Commit:
   ```bash
   git add -A
   git commit -m "..."
   ```
4. Push only if a remote exists and the user asked for it:
   ```bash
   git push
   ```
5. Update:
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`

Final state:

- Phase: `DONE`
- Owner: `KIMI_CODE` (user accepts next)
