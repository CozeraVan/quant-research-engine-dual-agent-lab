# Task Handoff

## Current Task

Add richer shared-cash failed-order diagnostics and summary analysis.

## Task ID

QRE-SHARED-FAILED-ORDER-SIDE-SUMMARY-REGRESSION-001

## Current Status

Reviewed and accepted locally.

## Current Owner

USER

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-CLI-TOPLEVEL-TYPE-REGRESSION-001`.
- Local checkpoint created: `75b42bc Lock manifest type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for invalid JSON and non-object manifest roots.
- Claude Code added 4 CLI regression tests: invalid JSON and non-object root across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `be62461 Lock malformed manifest roots at the CLI boundary`.
- Next task selected: CLI regression coverage for malformed manifest file entries.
- Claude Code added 4 CLI regression tests: non-object file entry and non-string required file-entry field across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `ac234d8 Lock manifest file-entry shape failures at the CLI boundary`.
- Next task selected: CLI regression coverage for schema-version type errors.
- Claude Code added 4 CLI regression tests: string and boolean `schema_version` across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `bdce0fa Lock schema-version type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for optional file-entry metadata type errors.
- Claude Code added 4 CLI regression tests: non-string optional `symbol` and `window` across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `a4693ab Lock optional manifest entry type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for optional `group_by` file-entry metadata type errors.
- Claude Code added 2 CLI regression tests: non-string optional `group_by` across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `0083c82 Lock optional group-by manifest type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for valid explicit `null` optional file-entry metadata.
- Claude Code added 2 CLI regression tests: explicit `null` optional metadata via `report-files --json` and `report-audit --json`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `cce750d Lock optional null manifest metadata at the CLI boundary`.
- Next task selected: CLI regression coverage for explicit `null` top-level `schema_version`.
- Claude Code added 2 CLI regression tests: explicit `schema_version: null` via `report-files --json` and `report-audit --json`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `eac50d3 Lock null schema version at the CLI boundary`.
- Next task selected: CLI regression coverage for `report-files --json --check-exists`.
- Claude Code added 2 CLI regression tests: `report-files --json --check-exists` when files exist and when files are missing.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `ff3732e Lock report-files JSON check-exists behavior`.
- Next task selected: CLI regression coverage for `report-files --json --validate-contents`.
- Claude Code added 2 CLI regression tests: `report-files --json --validate-contents` when files are valid and when files have structural issues.
- Codex review passed with no Required Fixes.
- Claude Code strengthened `test_cli_report_audit_json_includes_issues_for_failures` with per-issue object field assertions for `missing_file` and `missing_columns`.
- Claude Code added per-issue `code` assertions: `missing_file_issue["code"] == "missing_file"` and `missing_columns_issue["code"] == "missing_columns"`.
- Codex prepared the next implementation brief for shared-cash failed-order diagnostics and summary analysis.
- Claude Code implemented `QRE-SHARED-FAILED-ORDER-SIDE-SUMMARY-REGRESSION-001`: added `failed_order_count_by_side` and `failed_order_notional_by_side` to `_failed_order_diagnostics` in `shared.py`, added side-level breakdown to `_failed_order_summary_items` in `io.py`, and added 3 tests across `test_portfolio_shared.py` and 2 updated tests in `test_portfolio_io.py`.
- Codex reviewed and accepted `QRE-SHARED-FAILED-ORDER-SIDE-SUMMARY-REGRESSION-001`.

## In Progress

None.

## Expected Files

- `src/quant_research_engine/portfolio/shared.py` (modified)
- `src/quant_research_engine/portfolio/io.py` (modified)
- `tests/test_portfolio_shared.py` (2 new tests)
- `tests/test_portfolio_io.py` (2 updated tests)

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_portfolio_shared.py -q` -> `20 passed`
- Last accepted focused validation: `uv run pytest tests/test_portfolio_io.py -q` -> `8 passed`
- Last accepted full validation: `uv run pytest -q` -> `238 passed in 2.22s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Side-level diagnostics are additive; existing failed-order behavior is preserved.
- Empty failed-orders path returns empty dicts for side keys.

## Next Suggested Step

User can review the local finalization or request the next task.
