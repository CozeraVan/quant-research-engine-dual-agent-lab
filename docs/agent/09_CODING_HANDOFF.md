# Coding Handoff

## Task ID

QRE-REPORT-ROLLING-WINDOW-SIZE-FILTER-PARITY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

Added optional `window_size` metadata parsing, filtering, and CLI surface parity across the report-manifest stack:

- **`ReportFile`**: Added `window_size: int | None = None` field. `from_mapping()` parses `window_size` from manifest JSON entries — absent or explicit `null` yields `None`; non-integer types (string, boolean) raise a manifest-specific `ValueError`.
- **`ReportManifest.files()` / `paths()` / `validate_contents()`**: Added `window_size: int | None = None` parameter. Uses `_matches_int()` helper to filter entries whose `window_size` matches the requested value.
- **CLI**: Added `--window-size <int>` to `qre report-files` and `qre report-audit`. Threaded through all manifest method calls. `report-files --json` surfaces `window_size` on matched file entries when present.
- **Tests**: 9 manifest tests (parsing, absent/null acceptance, string/boolean rejection, `files()`/`paths()`/`validate_contents()` filtering) + 5 CLI tests (`--window-size` filter, JSON inclusion/omission/null). Total: 197 passed in 2.32s.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — Added `window_size` field to `ReportFile`, parsing in `from_mapping()`, `_matches_int` helper, `window_size` parameter on `files()`/`paths()`/`validate_contents()`.
- `src/quant_research_engine/apps/cli.py` — Added `--window-size` argument to `report-files` and `report-audit` parsers; threaded `window_size` through all manifest calls; added `window_size` to `report-files --json` output.
- `tests/test_portfolio_report_manifest.py` — 9 new tests for parsing, type rejection, and filtering behavior.
- `tests/test_cli.py` — 5 new tests for CLI filtering and JSON output.

## Validation Results

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 197 passed in 2.32s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Constraints

- Manifest schema version unchanged.
- Existing `role`, `symbol`, `window`, `group_by` filters preserved.
- Numeric `window_size` filtering independent of string `window` filtering.
- No changes to `docs/legacy/**`.
- No changes to rolling artifact filenames, roles, or output-generation logic.

## Git State

- Branch: `master`
- Last finalized implementation commit: `de37afd`, `Close batch grouped manifest header audit gap`
- Current changes are uncommitted (awaiting Codex review).

## Next Suggested Step

Codex should review the implementation, run validation, and write `10_REVIEW_REPORT.md`.
