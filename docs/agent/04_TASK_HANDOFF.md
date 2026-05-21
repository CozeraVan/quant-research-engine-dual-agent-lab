# Task Handoff

## Current Task

Add CLI regression coverage for invalid rolling-artifact `window_size` manifest metadata.

## Task ID

QRE-CLI-WINDOW-SIZE-METADATA-TYPE-REGRESSION-001

## Current Status

Accepted locally by Codex review. Ready for local git finalization.

## Current Owner

CODEX

## Completed

- Codex finalized `QRE-DOCS-ROLLING-WINDOW-SIZE-FILTER-USAGE-001` as local commit `22fd3d1`, `Document rolling window-size report filters`.
- Claude Code added 4 CLI regression tests in `tests/test_cli.py`:
  - `test_cli_report_files_reports_string_window_size`: `window_size: "20"` at the `report-files` boundary → exit code 2 + manifest-specific error on stderr.
  - `test_cli_report_files_reports_boolean_window_size`: `window_size: true` at the `report-files` boundary → exit code 2 + manifest-specific error on stderr.
  - `test_cli_report_audit_reports_string_window_size`: `window_size: "20"` at the `report-audit` boundary → exit code 2 + manifest-specific error on stderr.
  - `test_cli_report_audit_reports_boolean_window_size`: `window_size: true` at the `report-audit` boundary → exit code 2 + manifest-specific error on stderr.
- No runtime or parser code changes; the existing manifest `from_path()` rejection path already works correctly.
- All 4 new tests reuse the existing manifest-specific error wording: `"manifest file entry field 'window_size' must be an integer or null, got <type> (entry key: <key>)"`.
- Codex re-ran validation and marked `10_REVIEW_REPORT.md` as PASS. The implementation satisfies the brief without changing parser or CLI behavior.

## Expected Files

- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 201 passed in 1.96s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed
- `scripts/git-finalize-check.sh` → passed (from `22fd3d1`)

## Known Risks

- Test-only; no runtime or parser behavior changed.
- Stderr assertions use `"must be an integer or null"` substring from the existing manifest error message — stable unless `report_manifest.py` changes its wording.
- Legacy archived docs untouched.

## Next Suggested Step

Codex should run finalization checks and create the local completion commit for `QRE-CLI-WINDOW-SIZE-METADATA-TYPE-REGRESSION-001`.
