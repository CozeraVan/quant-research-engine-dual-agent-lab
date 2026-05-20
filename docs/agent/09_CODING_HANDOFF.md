# Coding Handoff

## Task ID

QRE-RUN-MANIFEST-CONTENT-VALIDATION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Fix applied for present-null required-field validation. Ready for Codex re-review.

## Implementation Summary

Added role-specific content validation for `run_manifest` entries in `ReportManifest.validate_contents()`. Validates required top-level fields (`schema_version`, `kind`, `run_id`, `command`, `strategy_path`, `artifacts`), enforces type constraints (string/null `run_id`, list-of-strings `artifacts`, integer-1 `schema_version`), and permits only `portfolio_backtest_run_manifest` and `evaluation_run_manifest` kinds. Present-but-null values for non-nullable required fields (`schema_version`, `kind`, `command`, `strategy_path`, `artifacts`) now produce `invalid_run_manifest_field` issues. `run_id: null` remains valid. Missing/invalid fields produce structured `ReportValidationIssue` entries with codes `missing_run_manifest_field` and `invalid_run_manifest_field`. Summary JSON validation is unchanged.

## Fix Applied

Codex review (`10_REVIEW_REPORT.md`) found that present-null values for required non-nullable fields bypassed validation because the code used `is not None` guards. Fixed by restructuring all field validators to use `"field" in payload` membership tests before checking for null, ensuring missing keys emit only `missing_run_manifest_field` while present-null keys emit `invalid_run_manifest_field`.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — added `_RUN_MANIFEST_KINDS` constant and `_validate_run_manifest()` function; modified `validate_contents()` to dispatch `run_manifest` role to the new validator; fixed present-null validation for 5 non-nullable fields using `"field" in payload` guards
- `tests/test_portfolio_report_manifest.py` — updated 2 existing tests with valid run-manifest data; added 14 new tests covering valid string/null run_id, evaluation kind, missing fields, invalid run_id type, invalid artifacts shape, invalid artifacts entry, unsupported kind, invalid schema_version, null schema_version, null kind, null command, null strategy_path, null artifacts, and explicit null run_id acceptance
- `tests/test_cli.py` — 2 new CLI regression tests: `report-audit --role run_manifest --json` catches malformed run manifest and accepts valid one

## Validation Results

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q  # 158 passed, 2 warnings in 1.76s
uv run pytest -q                                                            # 346 passed, 2 warnings in 3.22s
scripts/check-progress-docs.sh                                              # passed
git diff --check                                                            # passed
```

Codex reproduction case (`schema_version`, `command`, `strategy_path`, `artifacts` all null): now returns 4 `invalid_run_manifest_field` issues (was 0).

## Constraints

- Keep validation focused on `run_manifest` content. ✅
- Preserve existing report manifest file-entry schema. ✅
- Keep `run_id` optional; null is valid. ✅
- Do not change evaluation, preflight, or portfolio math. ✅
- Summary JSON validation unchanged. ✅
- Required non-null fields reject present-null values. ✅

## Git State

- Branch: `master`
- All code and doc changes uncommitted.
- Ready for Codex re-review.

## Next Suggested Step

Codex should re-review the fix and produce an updated `10_REVIEW_REPORT.md`.
