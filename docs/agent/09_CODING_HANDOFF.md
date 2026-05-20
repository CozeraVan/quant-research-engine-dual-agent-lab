# Coding Handoff

## Task ID

QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Fixed. Ready for Codex re-review.

## Fix Summary

Codex review found that `write_shared_cash_result(..., group_by=[...])` failed when `result.failed_orders` was an empty no-column DataFrame (the real engine produces `pd.DataFrame([])` for a run with no failed orders). The three summarizer functions checked column membership before emptiness, so a no-column empty frame raised `ValueError`.

Fix: moved the `empty` check before the column membership check in all three functions. Empty frames now always return a stable empty output DataFrame with proper column headers. Non-empty frames missing the requested group column still raise `ValueError`.

## Changes Since Last Review

- `src/quant_research_engine/portfolio/analytics.py`: reordered empty-vs-column checks in `summarize_shared_orders_by`, `summarize_shared_trades_by`, `summarize_shared_failed_orders_by`
- `tests/test_portfolio_analytics.py`: 3 new tests (`test_summarize_shared_*_by_handles_no_column_empty_frame`)
- `tests/test_portfolio_io.py`: 1 new integration test (`test_write_shared_cash_result_grouped_with_no_column_empty_failed_orders`) using realistic no-column `pd.DataFrame()` for failed_orders
- `docs/agent/09_CODING_HANDOFF.md`: updated with fix
- `docs/agent/04_TASK_HANDOFF.md`: updated status
- `docs/agent/05_PROGRESS.md`: updated evidence
- `docs/agent/11_AGENT_STATE.md`: updated phase
- `docs/agent/12_AGENT_BOARD.md`: updated for Codex

## Full Implementation Summary (original + fix)

- Added `summarize_shared_orders_by()`, `summarize_shared_trades_by()`, and `summarize_shared_failed_orders_by()` analytics helpers in `portfolio/analytics.py`. Each groups by a requested metadata column and produces row-based diagnostic summaries with counts, notional, and cost breakdowns. All three safely handle empty no-column DataFrames by returning stable empty outputs with correct column headers.
- Added `--group-by` CLI argument to `backtest-shared` (zero or more column names via `nargs="*"`). Unioned with `--metadata-columns` so group-by columns are always available in output rows.
- Updated `write_shared_cash_result()` to accept `group_by: list[str] | None = None` and write grouped CSV artifacts: `orders_by_<column>.csv`, `trades_by_<column>.csv`, `failed_orders_by_<column>.csv`.
- Added manifest roles `shared_orders_group_summary`, `shared_trades_group_summary`, `shared_failed_orders_group_summary` with validation columns in `_REQUIRED_COLUMNS_BY_ROLE`.
- Added `_shared_manifest_group_by()` helper and wired `group_by` metadata into shared-cash manifest entries.
- Updated `_shared_report_paths()` to include grouped artifact labels in summary markdown.
- Recorded `group_by` in `run_manifest.json` request payload for `backtest-shared --output-dir`.
- Printed grouped summaries to stdout when `--group-by` is requested.

## Files Changed

- `src/quant_research_engine/portfolio/analytics.py` — three shared-cash group summary functions with empty no-column handling
- `src/quant_research_engine/portfolio/io.py` — `write_shared_cash_result()` accepts `group_by`; manifest helpers
- `src/quant_research_engine/portfolio/report_manifest.py` — three new validation roles
- `src/quant_research_engine/apps/cli.py` — `--group-by` flag, unioned with `metadata_columns`, passed to writer
- `tests/test_portfolio_analytics.py` — 15 tests (12 original + 3 no-column empty fix)
- `tests/test_portfolio_io.py` — 6 tests (5 original + 1 no-column empty integration)
- `tests/test_cli.py` — 1 test for `backtest-shared --group-by`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Results

```bash
uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q  # 179 passed in 2.32s
uv run pytest -q                                                                              # 315 passed in 3.00s
scripts/check-progress-docs.sh                                                                # passed
git diff --check                                                                              # passed
```

## Constraints

- Preserve default shared-cash output behavior when `--group-by` is omitted. ✅
- Keep grouped summaries row-based and diagnostic. ✅
- Do not implement shared-cash group return attribution or group equity curves. ✅
- Do not change shared-cash simulation math, order selection, cash accounting, risk exits, rebalancing, or market validation. ✅
- Missing requested group columns fail clearly for non-empty frames. ✅
- Empty no-column DataFrames (real engine output) produce stable empty grouped CSVs. ✅
- Keep report manifests compatible with `report-files` and `report-audit`. ✅
- Do not push. ✅

## Git State

- Branch: `master`
- All code and doc changes uncommitted.
- Ready for Codex re-review.
