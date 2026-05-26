# Coding Handoff

## Task ID

QRE-PORTFOLIO-BASELINE-COMPARISON-001

## Written By

CODEX (brief), CLAUDE_CODE (implementation)

## Status

IMPLEMENTED

## Current Owner

CODEX (review)

## Implementation Summary

Populated buy-and-hold baseline comparison fields across single-symbol, batch, and full-market reporting paths. Added industry_group to batch metadata passthrough. Extended batch summary metrics aggregation with buy-hold and excess return statistics.

## Files Changed

- `src/quant_research_engine/portfolio/single_symbol.py`:
  - `_build_summary()` now accepts `frame: pd.DataFrame` parameter and computes `buy_hold_return` from first entry price to last mark price, plus `excess_return_vs_buy_hold`.
  - `_empty_result()` includes `buy_hold_return: None` and `excess_return_vs_buy_hold: None`.
  - `run()` passes `working` frame to `_build_summary()`.

- `src/quant_research_engine/portfolio/batch.py`:
  - Added `industry_group` to `SUMMARY_METADATA_COLUMNS`.
  - Buy-and-hold fields flow through automatically via `_summary_row()` copying `result.summary`.

- `src/quant_research_engine/portfolio/analytics.py`:
  - `summarize_batch_summary()` now aggregates `buy_hold_return`, `mean_buy_hold_return`, `median_buy_hold_return`, `mean_excess_return_vs_buy_hold`, `median_excess_return_vs_buy_hold`.
  - Empty summary case includes new fields as `None`.

- `tests/test_portfolio_single_symbol.py`:
  - Added `test_single_symbol_backtest_summary_includes_buy_hold_return` — verifies buy_hold_return and excess_return_vs_buy_hold computed correctly.
  - Added `test_single_symbol_backtest_buy_hold_return_is_none_for_empty_frame` — verifies None for empty symbol frame.

- `tests/test_portfolio_batch.py`:
  - Added `test_batch_backtest_includes_industry_group_in_metadata` — verifies industry_group flows through.
  - Added `test_batch_backtest_summary_includes_buy_hold_fields` — verifies buy_hold_return and excess_return_vs_buy_hold columns in batch summary.
  - Added `test_batch_backtest_summary_metrics_includes_buy_hold_aggregates` — verifies aggregate buy-hold stats in summary_metrics.

- `tests/test_portfolio_analytics.py`:
  - Added `test_summarize_batch_summary_aggregates_buy_hold_metrics` — verifies mean/median buy-hold and excess return aggregation.
  - Extended `test_summarize_batch_summary_handles_empty_summary` with new field assertions.

## Behavior Summary

- Single-symbol `_build_summary()` computes `buy_hold_return` from the first bar's entry price (open) to the last bar's mark price (close). If the frame is empty or missing required columns, the field is `None`.
- `excess_return_vs_buy_hold` = `total_return - buy_hold_return`.
- Batch `_summary_row()` propagates buy-hold fields from single-symbol results automatically.
- `summarize_batch_summary()` aggregates buy-hold returns (mean, median) and excess returns (mean, median) across all symbols.
- `build_symbol_performance()` batch mode already reads `buy_hold_return` and `excess_return_vs_buy_hold` from the summary DataFrame — these now flow through fully.
- `build_strategy_performance()` batch mode reads `buy_hold_return` and `excess_return_vs_buy_hold` from `summary_metrics`.
- `industry_group` is now included in default batch metadata columns alongside `industry`.
- Shared-cash paths remain unchanged.

## Validation Output

```
uv run pytest -q tests/test_portfolio_single_symbol.py tests/test_portfolio_batch.py → 20 passed
uv run pytest -q tests/test_portfolio_analytics.py → 26 passed
uv run pytest -q tests/test_full_market_report.py tests/test_cli.py tests/test_portfolio_benchmark.py → 484 passed, 2 warnings
uv run pytest -q → 895 passed, 2 warnings
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Handoff Back To Codex

Implementation ready for Codex review. Buy-and-hold baseline, industry_group passthrough, and excess-return comparison are wired end-to-end from single-symbol through batch/full-market reporting.
