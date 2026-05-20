# Task Handoff

## Current Task

Wire batch backtest `group_by` metadata passthrough for optional upstream columns.

## Task ID

QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001

## Current Status

Accepted locally.

## Current Owner

USER

## Completed

- Added `summary_metadata_columns: list[str] | None = None` to `BatchBacktestRequest`.
- Updated `BatchBacktestEngine.run()` to thread extra metadata columns through `_summary_row()` → `_metadata_row()`.
- Updated `_metadata_row()` to merge requested extra columns with the fixed `SUMMARY_METADATA_COLUMNS` list, avoiding duplicates.
- Updated CLI `backtest-batch` to pass `--group-by` columns as `summary_metadata_columns` to `BatchBacktestRequest`.
- Added 4 engine tests: default columns preserved, extra columns flow into summary, absent columns skipped, no duplicate columns.
- Added 1 CLI test: `backtest-batch --group-by sector` prints grouped output for passthrough column.

## In Progress

None.

## Expected Files

- `src/quant_research_engine/portfolio/batch.py` (modified)
- `src/quant_research_engine/apps/cli.py` (modified)
- `tests/test_portfolio_batch.py` (4 new tests)
- `tests/test_cli.py` (1 new test)

## Validation Baseline

- `uv run pytest tests/test_portfolio_batch.py tests/test_cli.py -q` -> `105 passed`
- `uv run pytest -q` -> `283 passed in 2.67s`
- `scripts/check-progress-docs.sh` -> passed (after doc update)
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

## Known Risks

- Missing group-by columns in the frame are silently skipped in `_metadata_row()`. Downstream `summarize_batch_by()` will raise a clear `ValueError` when the column is absent from the summary.
- No schema guesses — columns are request-driven only.
- Default batch summary behavior unchanged when `summary_metadata_columns` is omitted.

## Next Suggested Step

None. Await user acceptance or next request.
