# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-TOPLEVEL-FIELDS-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Scope Summary

- Add CLI regression coverage so `report-files` and `report-audit` both surface missing top-level `kind` and `files` with exit code 2 and clear stderr.
- Preserve existing CLI exit-code and stderr behavior for valid and previously-tested invalid manifests.

## Files Changed

- `tests/test_cli.py` — added 4 regression tests:
  - `test_cli_report_files_reports_missing_kind`
  - `test_cli_report_files_reports_missing_files`
  - `test_cli_report_audit_reports_missing_kind`
  - `test_cli_report_audit_reports_missing_files`

## Validation Results

```bash
uv run pytest tests/test_cli.py -q  # 61 passed in 1.07s
uv run pytest -q                     # 205 passed in 1.98s
scripts/check-progress-docs.sh       # passed
git diff --check                     # passed
```

## Constraints

- Do not change valid-manifest behavior. ✅ preserved
- Do not modify CLI code unless strictly necessary. ✅ no CLI changes needed
- Do not modify forbidden files from the brief. ✅ compliant
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Uncommitted changes: 1 test file + docs
- Last commit: `53f9aba Keep missing manifest files distinct from empty manifests`
