# Coding Handoff

## Task ID

QRE-REPORT-AUDIT-JSON-ISSUE-PAYLOAD-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Locally finalized.

## Scope Summary

- Strengthened `test_cli_report_audit_json_includes_issues_for_failures` with per-issue object field assertions (`key`, `code`, `path`, `message`) for `missing_file` and `missing_columns` issue payloads.

## Files Changed

- `tests/test_cli.py` — strengthened existing test:
  - `test_cli_report_audit_json_includes_issues_for_failures` — now asserts all 4 fields per issue object: `key`, `code`, `path`, `message`

## Validation Results

```bash
uv run pytest tests/test_cli.py -q  # 91 passed in 1.23s
uv run pytest -q                     # 235 passed in 2.17s
scripts/check-progress-docs.sh       # passed
git diff --check                     # passed
```

## Constraints

- Do not change valid-manifest behavior. ✅ preserved
- Do not modify CLI code unless strictly necessary. ✅ no CLI changes needed
- Do not modify forbidden files. ✅ compliant
- Preserve issue object fields and issue counts. ✅ `code` asserted per-issue
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Last local commit: `dff2889 Lock report-audit JSON issue payload fields at the CLI boundary`
- No pending finalization for this task.
