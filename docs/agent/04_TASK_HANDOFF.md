# Task Handoff

## Current Task

Add output artifacts and manifests for `qre eval-config`.

## Task ID

QRE-EVAL-CONFIG-OUTPUT-ARTIFACTS-REGRESSION-001

## Current Status

Implemented. Ready for Codex review.

## Current Owner

CODEX

## Completed

- Added `evaluation_report_manifest` kind to `_SUPPORTED_MANIFEST_KINDS` in `report_manifest.py`.
- Added evaluation artifact role column requirements (`events`, `evaluation_summary`, `ic_summary`, `quantile_summary`, `evaluation_group_summary`) to `_REQUIRED_COLUMNS_BY_ROLE`.
- Added `--output-dir` CLI argument to `eval-config` subcommand.
- Implemented `_write_evaluation_output()` and `_eval_manifest_role()` helpers in `cli.py`.
- When `--output-dir` is provided, writes: `events.csv` (always), `summary.csv` (non-empty), `ic_summary.csv` (non-empty), `quantile_summary.csv` (non-empty), `group_summary.csv` (non-empty), `run_manifest.json`, and `report_manifest.json`.
- `run_manifest.json` records safe run inputs (command, strategy_path, dates, codes, cost rate or market-profile path, group columns, artifacts) without sensitive connection values.
- `report_manifest.json` uses kind `evaluation_report_manifest` and can be loaded/validated by `ReportManifest`.
- Added 2 CLI regression tests and 8 manifest validation tests.
- Existing stdout behavior preserved; output-dir is additive and optional.
- Run-manifest provenance now includes `market_profile` when that path is the source of the effective cost rate.

## In Progress

None. Ready for Codex review.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py` (modified)
- `src/quant_research_engine/apps/cli.py` (modified)
- `tests/test_cli.py` (2 new tests)
- `tests/test_portfolio_report_manifest.py` (8 new tests)

## Validation Baseline

- `uv run pytest tests/test_cli.py -q` -> `95 passed in 1.57s`
- `uv run pytest tests/test_portfolio_report_manifest.py -q` -> `34 passed`
- `uv run pytest -q` -> `265 passed in 2.83s`
- `scripts/check-progress-docs.sh` -> passed (after doc update)
- `git diff --check` -> passed

## Known Risks

- Output-dir is additive and optional; existing stdout behavior unchanged.
- Existing portfolio report-manifest parsing remains compatible.
- Run manifests omit sensitive connection values.
- No evaluation math changed.

## Next Suggested Step

Codex should review and run One-Shot Review-Finalize-Next.
