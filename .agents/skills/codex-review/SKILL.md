---
name: codex-review
description: Codex review flow that checks implementation against the brief and writes Review Report.
---

# Codex Review

Use this when Codex is the current owner and phase is `CODEX_REVIEWING`.

Do not implement code unless explicitly requested.

Read:

- `AGENTS.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`

Inspect:

```bash
git status
git diff --name-only HEAD
git diff HEAD
```

Write:

- `docs/agent/10_REVIEW_REPORT.md`

If Required Fixes exist:

- Phase: `CLAUDE_FIXING`
- Owner: `CLAUDE_CODE`

If review passes:

- Phase: `USER_ACCEPTANCE`
- Owner: `USER`
