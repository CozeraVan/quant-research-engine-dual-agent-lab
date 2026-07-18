---
name: intake-change
description: Turn a new idea, feature, refactor, or deletion request into a formal Change Request.
---

# Intake Change Request

Do not modify business code.

Create a new file under:

`docs/agent/change_requests/`

Use the next available ID:

`CR-0001-short-name.md`

Include:

1. Background
2. Goal
3. User scenario
4. In Scope
5. Out of Scope
6. Affected requirements
7. Protected requirements
8. Suggested tasks
9. Acceptance criteria
10. Risks
11. Implementation notes
12. Proposed agent state transition

After creating the file, update `docs/agent/11_AGENT_STATE.md` to:

- Phase: `PLANNING`
- Owner: `KIMI_CODE`

Then summarize and wait for user confirmation before writing the Implementation Brief.
