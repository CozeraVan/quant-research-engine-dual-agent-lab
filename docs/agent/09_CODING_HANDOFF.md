# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-SCHEMA-VERSION-NULL-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Scope Summary

- Add CLI regression coverage so `report-files --json` and `report-audit --json` both accept explicit `schema_version: null` and report it as JSON `null`.

## Files Changed

- `tests/test_cli.py` — added 2 regression tests:
  - `test_cli_report_files_json_accepts_null_schema_version`
  - `test_cli_report_audit_json_accepts_null_schema_version`

## Validation Results

```bash
uv run pytest tests/test_cli.py -q  # 87 passed in 1.21s
uv run pytest -q                     # 231 passed in 2.19s
git diff --check                     # passed
```

## Constraints

- Do not change valid-manifest behavior. ✅ preserved
- Do not modify CLI code unless strictly necessary. ✅ no CLI changes needed
- Do not modify forbidden files. ✅ compliant
- Preserve schema-version validation semantics. ✅ preserved
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Uncommitted changes: 1 test file + docs
- Last commit: `cce750d Lock optional null manifest metadata at the CLI boundary`
