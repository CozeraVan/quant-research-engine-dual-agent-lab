---
name: git-finalize
description: Final git verification, commit, and push flow. Codex-owned by default.
---

# Git Finalize

This flow is Codex-owned by default.

Use only when:

- Phase is `CODEX_GIT_FINALIZING`
- Owner is `CODEX`
- Review has passed
- User has approved finalization or standing approval exists

Required checks:

```bash
git status
git diff --name-only HEAD
scripts/check-progress-docs.sh
scripts/git-finalize-check.sh
```

Then:

1. Propose commit message.
2. Confirm no secrets are included.
3. Commit:
   ```bash
   git add -A
   git commit -m "..."
   ```
4. Push:
   ```bash
   git push
   ```
5. Update:
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`

Final state:

- Phase: `DONE`
- Owner: `USER`
