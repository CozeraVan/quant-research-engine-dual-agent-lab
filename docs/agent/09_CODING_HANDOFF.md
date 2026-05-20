# Coding Handoff

## Task ID

QRE-REPORT-GROUP-BY-CONTENT-CONSISTENCY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Fix applied. Ready for Codex re-review.

## Implementation Summary

Added `_validate_csv_group_by_consistency()` to `ReportManifest.validate_contents()`. After required-column validation passes for grouped artifact entries with manifest `group_by` metadata, the new check reads the CSV `group_by` column and verifies every non-empty cell matches the manifest entry's `group_by` value. Mismatched values produce a `group_by_mismatch` validation issue including both the expected manifest value and the observed CSV values.

The check is scoped only to entries that have manifest `group_by` metadata — entries without it (including the combined evaluation `group_summary.csv`) are not checked.

## Required Fix Applied (2026-05-21)

Gated `_validate_csv_group_by_consistency()` on successful required-column validation: `validate_contents()` now only runs the `group_by` consistency check when `_validate_csv_columns()` returned no issues for that file. A malformed grouped file missing a required column and containing mismatched `group_by` values now only emits `missing_columns`.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — Added `_validate_csv_group_by_consistency()` function; wired call in `validate_contents()` after `_validate_csv_columns()` only when column validation passes.
- `tests/test_portfolio_report_manifest.py` — Added 9 tests: mismatch detection for evaluation, shared orders, shared trades, shared failed orders; matching acceptance for evaluation and shared orders; no-check-when-no-manifest-metadata; multi-value mismatch message; regression for missing-columns-skips-group-by-check.
- `tests/test_cli.py` — Added 2 CLI tests: `test_cli_report_audit_group_by_mismatch` for stderr surface, `test_cli_report_audit_group_by_mismatch_json` for JSON issue payload.

## Validation Results

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 175 passed in 1.84s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Constraints

- Manifest schema version unchanged.
- Combined `group_summary.csv` without manifest `group_by` metadata still passes unchanged.
- Batch grouped outputs (window_summary, window_ranked_symbols) not affected — their CSV files lack a literal `group_by` column.
- No changes to `docs/legacy/**`.
- `group_by` consistency check only runs after required-column validation passes.

## Git State

- Branch: `master`
- Last finalized implementation commit: `5fc7605`, `Clarify evaluation grouped artifact usage`
- Current changes are uncommitted (awaiting Codex review).

## Next Suggested Step

Codex should re-review the fix, run validation, and write updated `10_REVIEW_REPORT.md`.
