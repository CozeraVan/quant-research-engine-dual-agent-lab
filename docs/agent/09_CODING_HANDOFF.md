# Coding Handoff

## Task ID

QRE-REPORT-AUDIT-JSON-ISSUE-PAYLOAD-REGRESSION-001

## Written By

CODEX

## Intended Implementer

CLAUDE_CODE

## Status

Ready for Claude Code implementation.

## Scope Summary

Add CLI regression coverage for exact `report-audit --json` issue object payload details for missing-file and missing-columns failures.

## Files To Change

Expected:

- `tests/test_cli.py`

Update after implementation:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Do not change production code unless the new tests expose a real command-boundary bug.

## Validation Required

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Handoff Notes

- Use existing `test_cli_report_audit_json_includes_issues_for_failures` as the local anchor.
- It is acceptable to strengthen that existing test or add focused adjacent tests.
- Assert issue object fields: `key`, `code`, `path`, and `message`.
- Keep the task test-only if existing CLI behavior already passes.

## Git State

- Branch: `master`
- Last accepted implementation commit: `43a17b7 Lock report-files JSON validate-contents behavior`
- Current task is ready for Claude Code.
- Do not push.
