# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-GROUP-BY-TYPE-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Scope Summary

- Add CLI regression coverage so `report-files` and `report-audit` both surface non-string optional file-entry `group_by` metadata with exit code 2 and clear stderr.

## Files Changed

- `tests/test_cli.py` — added 2 regression tests:
  - `test_cli_report_files_reports_non_string_optional_group_by`
  - `test_cli_report_audit_reports_non_string_optional_group_by`

## Validation Results

```bash
uv run pytest tests/test_cli.py -q  # 83 passed in 1.16s
uv run pytest -q                     # 227 passed in 2.09s
git diff --check                     # passed
```

## Constraints

- Do not change valid-manifest behavior. ✅ preserved
- Do not modify CLI code unless strictly necessary. ✅ no CLI changes needed
- Do not modify forbidden files. ✅ compliant
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Uncommitted changes: 1 test file + docs
- Last commit: `a4693ab Lock optional manifest entry type failures at the CLI boundary`
