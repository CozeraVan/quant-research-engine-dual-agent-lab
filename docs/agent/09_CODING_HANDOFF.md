# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-MALFORMED-ROOT-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Scope Summary

- Add CLI regression coverage so `report-files` and `report-audit` both surface invalid JSON and non-object manifest roots with exit code 2 and clear stderr.

## Files Changed

- `tests/test_cli.py` — added 4 regression tests:
  - `test_cli_report_files_reports_invalid_json_text`
  - `test_cli_report_files_reports_non_object_root`
  - `test_cli_report_audit_reports_invalid_json_text`
  - `test_cli_report_audit_reports_non_object_root`

## Validation Results

```bash
uv run pytest tests/test_cli.py -q  # 69 passed in 1.02s
uv run pytest -q                     # 213 passed in 1.96s
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
- Last commit: `75b42bc Lock manifest type failures at the CLI boundary`
