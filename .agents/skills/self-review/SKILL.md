---
name: self-review
description: Single-agent self-review flow that checks the implementation against the brief and writes the Review Report.
---

# Self Review

Use this when the phase is `SELF_REVIEW`.

Because the same agent planned and implemented the work, review actively: assume something is wrong and look for it. Do not rubber-stamp your own diff.

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

Check at minimum:

- Implementation matches the brief's scope and non-goals; no unrelated changes.
- LOCKED requirements are intact.
- Validation commands ran and passed (or gaps are documented).
- `docs/agent/` memory files are updated in the same change (R-AGENT-002).

Write:

- `docs/agent/10_REVIEW_REPORT.md`

If Required Fixes exist:

- Phase: `IMPLEMENTING`

If review passes:

- Phase: `AWAITING_GIT_APPROVAL`
- Propose the commit message to the user and wait for explicit approval.
