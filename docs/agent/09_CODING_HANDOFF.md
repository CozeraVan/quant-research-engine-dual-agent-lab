# Coding Handoff

## Task ID

QRE-REPORT-BATCH-GROUP-BY-HEADER-CONSISTENCY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

Added `_validate_csv_batch_group_by_header()` to `ReportManifest.validate_contents()`. After required-column validation passes for batch grouped artifact entries with manifest `group_by` metadata, the new check reads the CSV header and verifies it contains a column named exactly the manifest entry's `group_by` value. Missing columns produce a `group_by_header_mismatch` validation issue including the expected manifest value and the observed CSV header columns.

The check is scoped to batch grouped roles (`_BATCH_GROUPED_ROLES`): `group_summary`, `group_ranked_symbols`, `window_summary`, `window_ranked_symbols`, `rolling_summary`, `rolling_ranked_symbols`. Evaluation/shared grouped roles continue to use `_validate_csv_group_by_consistency()` for literal `group_by` column values. Entries without manifest `group_by` metadata are not checked by either path.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — Added `_BATCH_GROUPED_ROLES` set; added `_validate_csv_batch_group_by_header()` function; wired call in `validate_contents()` after `_validate_csv_columns()` only for batch grouped roles.
- `tests/test_portfolio_report_manifest.py` — Added 6 tests: mismatch detection for `group_summary`, `window_summary`, `window_ranked_symbols`; matching acceptance; missing-columns-skips-header-check regression; no-check-without-manifest-group-by.
- `tests/test_cli.py` — Added 2 CLI tests: `test_cli_report_audit_batch_header_mismatch` for stderr surface, `test_cli_report_audit_batch_header_mismatch_json` for JSON issue payload.

## Validation Results

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 183 passed in 1.91s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Constraints

- Manifest schema version unchanged.
- Evaluation/shared grouped consistency checks from `a3768fb` preserved.
- Batch grouped entries without manifest `group_by` metadata not checked.
- No changes to `docs/legacy/**`.

## Git State

- Branch: `master`
- Last finalized implementation commit: `a3768fb`, `Tighten grouped artifact audit consistency`
- Current changes are uncommitted (awaiting Codex review).

## Next Suggested Step

Codex should review the implementation, run validation, and write `10_REVIEW_REPORT.md`.
