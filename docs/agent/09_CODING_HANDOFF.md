# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-NULL-METADATA-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Scope Summary

- Add CLI regression coverage so `report-files --json` and `report-audit --json` both accept explicit `null` optional file-entry metadata (`symbol`, `window`, `group_by`) with exit code 0.

## Files Changed

- `tests/test_cli.py` — added 2 regression tests:
  - `test_cli_report_files_json_accepts_null_optional_metadata`
  - `test_cli_report_audit_json_accepts_null_optional_metadata`

## Validation Results

```bash
uv run pytest tests/test_cli.py -q  # 85 passed in 1.17s
uv run pytest -q                     # 229 passed in 2.08s
git diff --check                     # passed
```

## Constraints

- Do not change valid-manifest behavior. ✅ preserved
- Do not modify CLI code unless strictly necessary. ✅ no CLI changes needed
- Do not modify forbidden files. ✅ compliant
- Do not change JSON serialization for null metadata. ✅ preserved (keys omitted when None)
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Uncommitted changes: 1 test file + docs
- Last commit: `0083c82 Lock optional group-by manifest type failures at the CLI boundary`
