# Task Handoff

## Current Task

Add a portfolio backtest run manifest for reproducible research runs.

## Task ID

QRE-PORTFOLIO-BACKTEST-RUN-MANIFEST-REGRESSION-001

## Current Status

Reviewed and accepted locally.

## Current Owner

USER

## Completed

- Claude Code implemented initial `run_manifest.json` for single, batch, shared backtests.
- Codex review round 1: run-manifest request payload incomplete for reproducibility. Fixed: added `market_profile` to all 3 backtest handlers, `group_by`/`group_rank_top_n` to batch, `benchmark_table`/`benchmark_code`/`benchmark_value_column` to shared.
- Codex review round 2: report manifest role mapping incomplete — `_batch_manifest_role()` returned `"artifact"` for `run_manifest` key instead of `"run_manifest"`, and `_shared_manifest_role()` relied on implicit fallthrough.
- Claude Code applied fix: added explicit `run_manifest` role mapping to both `_batch_manifest_role()` and `_shared_manifest_role()`.
- Updated 2 existing tests to assert `role == "run_manifest"` in emitted report manifests.
- Added 2 end-to-end tests proving `ReportManifest.validate_contents(role="run_manifest")` passes on emitted report manifests from both batch and shared writers.
- Full validation: 246 passed in 2.36s.
- Codex re-reviewed and accepted the completed implementation.

## In Progress

None.

## Expected Files

- `src/quant_research_engine/apps/cli.py` (modified)
- `src/quant_research_engine/portfolio/io.py` (modified)
- `src/quant_research_engine/portfolio/report_manifest.py` (modified)
- `tests/test_portfolio_io.py` (4 new + updated)
- `tests/test_portfolio_report_manifest.py` (2 new)

## Validation Baseline

- Last accepted focused: `uv run pytest tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py -q` -> `40 passed`
- Last accepted full: `uv run pytest -q` -> `246 passed in 2.36s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Run manifest is additive; existing behavior preserved.
- Sensitive connection values are omitted.
- `market_profile` stored as file path string or `"built-in"`; benchmark fields only present when user provides them.
- `run_manifest` role mapping is now explicit in both `_batch_manifest_role()` and `_shared_manifest_role()`.

## Next Suggested Step

Codex should create the local checkpoint and prepare the next implementation brief when a new self-contained task is selected.
