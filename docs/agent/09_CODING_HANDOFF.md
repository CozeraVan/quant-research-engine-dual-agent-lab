# Coding Handoff

## Task ID

QRE-SHARED-CASH-FULL-MARKET-REPORT-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Objective

Add shared-cash support to `write_full_market_report()` and wire it into `write_shared_cash_result()` so that `qre research-run --backtest-mode shared` produces the same full-market report bundle as batch mode.

## Implementation Summary

- `src/quant_research_engine/portfolio/full_market_report.py` — added `engine_mode: str = "batch"` parameter to all 6 builders and the entry point:
  - `build_trades_ledger(results, engine_mode="batch")` — shared-cash branch iterates flat orders DataFrame via `to_dict("records")`.
  - `build_round_trips(results, engine_mode="batch")` — shared-cash branch iterates flat trades DataFrame.
  - `build_symbol_performance(summary=None, engine_mode="batch", round_trips=None, orders=None, failed_orders=None)` — shared-cash branch computes per-symbol stats from `round_trips.groupby("symbol")`; uses `failed_orders.groupby("symbol").size()` for failed_order_count; sets sharpe/max_drawdown/board/industry to None.
  - `build_full_market_equity_curve(results, engine_mode="batch")` — shared-cash branch takes a single equity curve DataFrame and computes `daily_return` + `cumulative_return`.
  - `build_strategy_performance(summary_metrics, summary=None, round_trips=None, engine_mode="batch")` — shared-cash branch maps summary dict keys directly; derives best/worst symbols from `round_trips.groupby("symbol")["net_pnl"].sum()`; nulls out buy_hold_return, excess_return, positive_symbol_rate, mean/median_symbol_return.
  - `write_full_market_report(result, output_dir, engine_mode="batch")` — shared-cash branch extracts `result.orders`, `result.trades`, `result.equity_curve`, `result.summary`, `result.failed_orders`; uses `full_market_equity_curve` as key to avoid collision with shared-cash's existing `equity_curve` entry.
- `src/quant_research_engine/portfolio/io.py`:
  - `write_shared_cash_result()` — added `write_full_market_report()` call with `engine_mode="shared_cash"` between run_manifest and summary_markdown writes; paths merged via `paths.update(full_market_paths)`.
  - `_shared_manifest_role()` — added 9 entries for full-market artifact roles (trades_ledger, round_trips, symbol_performance, strategy_performance, full_market_equity_curve, drawdown_curve, trade_analysis, capital_usage, backtest_report).
  - `_shared_report_paths()` — added labels dict entries for all 9 full-market artifacts.
- `tests/test_full_market_report.py` — 6 new test classes (17 tests):
  - `TestBuildTradesLedgerSharedCash` (3 tests): empty, flat orders, order_reason preserved.
  - `TestBuildRoundTripsSharedCash` (2 tests): empty, flat trades with returns.
  - `TestBuildSymbolPerformanceSharedCash` (3 tests): empty, per-symbol aggregation with null sharpe/max_drawdown/board/industry, failed_order_count=0.
  - `TestBuildFullMarketEquityCurveSharedCash` (2 tests): empty, enriched with daily_return/cumulative_return.
  - `TestBuildStrategyPerformanceSharedCash` (3 tests): summary dict key mappings, null fields, best/worst from round_trips.
  - `TestWriteFullMarketReportSharedCash` (3 tests): all 9 artifacts written and exist, overview engine_mode, empty result handling.
- `tests/test_portfolio_io.py` — 2 new integration tests:
  - `test_write_shared_cash_result_includes_full_market_files` — verifies all 9 full-market keys in paths dict, files exist on disk, manifest roles include full-market roles, existing shared-cash roles preserved, markdown includes file references.
  - `test_shared_cash_manifest_validates_full_market_roles` — validates ReportManifest contents pass with no issues.

## Validation

```bash
uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py -q
# 19 new tests passed

uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_full_market_report.py tests/test_research_run.py -q
# 519 passed, 2 warnings in 5.91s

scripts/check-progress-docs.sh
# passed

git diff --check
# passed
```
