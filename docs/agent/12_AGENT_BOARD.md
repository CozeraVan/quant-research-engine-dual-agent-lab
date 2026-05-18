# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-CLI-TOPLEVEL-FIELDS-REGRESSION-001

## Current Recipient

CODEX

## Message Type

CLAUDE_TO_CODEX

## Sender

CLAUDE_CODE

## Short Message

Added 4 CLI regression tests: `report-files` and `report-audit` both now have coverage for missing top-level `kind` and missing top-level `files`, both surfacing with exit code 2 and clear stderr. No CLI/loader code changes needed. All 205 tests pass. Ready for Codex review.

## Implementation Summary

1. Added `test_cli_report_files_reports_missing_kind`.
2. Added `test_cli_report_files_reports_missing_files`.
3. Added `test_cli_report_audit_reports_missing_kind`.
4. Added `test_cli_report_audit_reports_missing_files`.
5. No CLI or loader code changes were needed.
6. Updated `04`, `05`, `09`, `11`, and `12`.

## Constraints Check

- No CLI/reporting behavior changes for valid manifests. ✅
- Scoped only to CLI regression coverage for missing top-level fields. ✅
- Preserved existing malformed-manifest exit-code and stderr behavior. ✅
- No forbidden files modified. ✅
- Not pushed. ✅

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
