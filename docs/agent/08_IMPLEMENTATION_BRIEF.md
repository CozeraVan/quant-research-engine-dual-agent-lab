# Implementation Brief

## Task ID

QRE-REPORT-DOCS-JSON-CLI-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Recent reporting CLI work added:

- `qre report-audit --json`
- `qre report-files --require-match`
- `qre report-files --json`

The README Report Artifact Checks section still documents only the older text-mode examples and `report-audit --require-match`. The next small task is to document the new script-friendly report CLI options.

## Goal

Update user-facing report artifact documentation so operators can discover and use strict matching and JSON output modes for report workflows.

## Non-Goals

- Do not change CLI behavior.
- Do not change tests unless a doc check already exists and must be updated.
- Do not change report artifact generation.
- Do not change manifest JSON shape.
- Do not modify old root progress docs.
- Do not alter locked requirements.

## Affected Files

Expected:

- `README.md`

Docs/handoff:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**`
- `tests/**` unless a doc validation test requires update
- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing README guidance.
- Do not present smoke outputs as research conclusions.
- Do not document credentials or local secrets.
- Keep examples script-friendly and local.

## Implementation Steps

1. Inspect the current README Report Artifact Checks section.
2. Add concise examples for:
   - `qre report-files --require-match`
   - `qre report-files --json`
   - `qre report-audit --json`
3. State that JSON modes are intended for scripts and emit machine-readable stdout.
4. Preserve existing text-mode examples.
5. Keep wording concise; do not add broad architecture explanation.
6. Update handoff/progress/state/board docs after implementation.

## Validation Plan

Run:

```bash
scripts/check-progress-docs.sh
git diff --check
```

If tests are not run because this is docs-only, document that in `09_CODING_HANDOFF.md`.

Optional if practical:

```bash
uv run pytest -q
```

## Acceptance Criteria

- [ ] README documents strict matching for `report-files`.
- [ ] README documents JSON output for `report-files`.
- [ ] README documents JSON output for `report-audit`.
- [ ] Existing examples remain valid and understandable.
- [ ] No business code changes.
- [ ] Progress docs check and whitespace check pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Documentation should not imply smoke reports are research conclusions.
- JSON examples should avoid requiring local DB access.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated docs rewrites.
3. Avoid modifying forbidden files.
4. Run validation commands where possible.
5. Update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/12_AGENT_BOARD.md`

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
