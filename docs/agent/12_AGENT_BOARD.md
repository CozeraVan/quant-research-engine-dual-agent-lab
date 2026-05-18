# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-CLI-FILE-ENTRY-SHAPE-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

Add CLI regression coverage so `report-files` and `report-audit` both surface non-object file entries and non-string required file-entry fields with exit code `2` and clear stderr, without changing valid-manifest behavior.

## Implementation Summary

1. Inspect existing malformed-manifest CLI tests in `tests/test_cli.py`.
2. Add `report-files` coverage for a non-object file entry.
3. Add `report-files` coverage for a non-string required file-entry field.
4. Add `report-audit` coverage for a non-object file entry.
5. Add `report-audit` coverage for a non-string required file-entry field.
6. Keep the task test-focused and touch CLI or loader code only if a real bug is exposed.
7. Update `04`, `05`, `09`, `11`, and `12`.

## Constraints Check

- No CLI/reporting behavior changes for valid manifests.
- Scoped only to CLI regression coverage for file-entry shape/type errors.
- Preserve existing malformed-manifest exit-code and stderr behavior.
- No forbidden files modified.
- Not pushed.

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
