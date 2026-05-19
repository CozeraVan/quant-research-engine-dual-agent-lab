# Implementation Brief

## Task ID

QRE-REPORT-AUDIT-JSON-ISSUE-PAYLOAD-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre report-audit --json` already has coverage for valid audits, zero-match failures, and mixed failure cases. The mixed failure coverage currently checks aggregate counts and issue codes, but it does not directly lock the full issue object payload shape that script consumers rely on: `key`, `code`, `path`, and `message`.

## Goal

Add CLI regression coverage for exact `report-audit --json` issue payload details while preserving existing audit JSON behavior.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags or normal CLI output for valid manifests.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not broaden this into report-audit redesign.
- Do not modify CLI or loader code unless a tiny adjustment is strictly necessary.

## Affected Modules

Expected:

- `tests/test_cli.py`

Optional only if strictly needed:

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/report_manifest.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**` outside `apps/cli.py` and `portfolio/report_manifest.py`
- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve report-audit JSON output behavior.
- Preserve issue object fields and issue counts for missing-file and missing-column failures.
- No database writes or credential handling.
- No unrelated CLI or reporting refactors.

## Implementation Steps

1. Inspect existing `report-audit --json` failure tests in `tests/test_cli.py`.
2. Add or strengthen coverage for a missing-file issue object with exact `key`, `code`, `path`, and message content.
3. Add or strengthen coverage for a missing-columns issue object with exact `key`, `code`, `path`, and message content.
4. Assert current command-boundary behavior: exit code `2`, JSON `status: failed`, issue counts remain correct, and issue payload fields are stable.
5. Do not modify CLI or loader code unless the tests expose a real bug that must be fixed.
6. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task adds regression coverage only unless a tiny bugfix is required.

## API / Interface Changes

Valid CLI behavior should remain unchanged.

`report-audit --json` issue objects should continue exposing stable `key`, `code`, `path`, and `message` fields.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_cli.py -q
```

Run full tests:

```bash
uv run pytest -q
```

Run workflow checks:

```bash
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `report-audit --json` missing-file issue objects expose stable `key`, `code`, `path`, and `message`.
- [ ] `report-audit --json` missing-columns issue objects expose stable `key`, `code`, `path`, and `message`.
- [ ] JSON `status`, `missing_files`, `validation_issues`, and issue counts remain correct.
- [ ] Existing valid `report-audit --json` behavior remains unchanged.
- [ ] Existing zero-match `report-audit --json --require-match` behavior remains unchanged.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new work scoped to CLI regression coverage.
- Avoid changing issue object field names or message wording unless a real bug is exposed.
- Do not introduce CLI behavior changes for valid manifests.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated refactors.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing code.
5. Run validation commands where possible.
6. Update:
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/12_AGENT_BOARD.md`

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
