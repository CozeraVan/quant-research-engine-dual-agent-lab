# Coding Handoff

## Task ID

QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Accepted locally.

## Implementation Summary

- Added `summary_metadata_columns: list[str] | None = None` to `BatchBacktestRequest`.
- Updated `BatchBacktestEngine.run()` to thread extra metadata columns through `_summary_row()` → `_metadata_row()`.
- Updated `_metadata_row()` to merge requested extra columns with the fixed `SUMMARY_METADATA_COLUMNS` (avoiding duplicates), then copy values from the first frame row for each symbol.
- Updated CLI `backtest-batch` to pass `--group-by` columns as `summary_metadata_columns` to `BatchBacktestRequest`, so grouped stdout and output-dir reports can use the passthrough metadata columns.
- `ResearchFrameAssembler`, `write_batch_result()`, and `summarize_batch_by()` require no changes — the existing group-by report paths work as long as the column is present in the summary.

## Files Changed

- `src/quant_research_engine/portfolio/batch.py` — added `summary_metadata_columns` to `BatchBacktestRequest`; threaded extra columns through `run()` → `_summary_row()` → `_metadata_row()`
- `src/quant_research_engine/apps/cli.py` — pass `args.group_by` as `summary_metadata_columns` to `BatchBacktestRequest`
- `tests/test_portfolio_batch.py` — 4 new tests: default columns preserved, extra columns in summary, absent column skipped, no duplicate columns
- `tests/test_cli.py` — 1 new test: `backtest-batch --group-by sector` prints grouped output

## Validation Results

```bash
uv run pytest tests/test_portfolio_batch.py tests/test_cli.py -q  # 105 passed
uv run pytest -q                                                    # 283 passed in 2.67s
scripts/check-progress-docs.sh                                      # passed (after doc update)
git diff --check                                                    # passed
```

## Constraints

- Preserve existing batch summary metadata columns by default. ✅ fixed SUMMARY_METADATA_COLUMNS unchanged.
- Keep the change additive and scoped. ✅ only new optional field; existing paths unchanged.
- Keep data access read-only. ✅ no upstream writes.
- Avoid benchmark and time-varying-status table guesses. ✅ not touched.
- Do not change portfolio simulation math. ✅ not touched.

## Git State

- Branch: `master`
- Codex review passed.
- Local finalization in progress.
