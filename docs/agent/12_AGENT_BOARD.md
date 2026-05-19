# Agent Board

## Current Task ID

QRE-REPORT-AUDIT-JSON-ISSUE-PAYLOAD-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

Local version management is complete for `QRE-REPORT-AUDIT-JSON-ISSUE-PAYLOAD-REGRESSION-001`. The test now asserts per-issue `key`, `code`, `path`, and `message` fields for both `missing_file` and `missing_columns`. Validation passed: 91 CLI tests, 235 full tests. Please take the next task from the updated workflow state.

## Implementation Summary

1. Added `assert missing_file_issue["code"] == "missing_file"` to the per-issue block.
2. Added `assert missing_columns_issue["code"] == "missing_columns"` to the per-issue block.
3. Each issue object now has all 4 stable fields asserted: `key`, `code`, `path`, `message`.
4. Updated `04`, `05`, `09`, `11`, and `12`.

## Constraints Check

- ✅ No CLI/reporting behavior changes for valid manifests.
- ✅ Scoped only to CLI regression coverage for `report-audit --json` issue payload details.
- ✅ All 4 issue object fields (`key`, `code`, `path`, `message`) asserted per-issue.
- ✅ No forbidden files modified.
- ✅ Not pushed.

## Expected Files

- `tests/test_cli.py`
- `src/**` only if a tiny bugfix is strictly necessary
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```
