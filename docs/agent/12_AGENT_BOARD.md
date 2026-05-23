# Agent Board

## Current Task ID

QRE-SHARED-CASH-FULL-MARKET-REPORT-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_REQUEST

## Sender

CLAUDE_CODE (acting planner — Codex unavailable)

## Short Message

Add shared-cash support for the full-market report bundle. Currently `write_full_market_report()` only works with `BatchBacktestResult`. Running `qre research-run --backtest-mode shared` produces no `trades_ledger.csv`, `round_trips.csv`, `backtest_report.xlsx`, etc. This task adds `engine_mode` parameter to all builders and wires the call into `write_shared_cash_result()`.

## Delivered Artifacts

- `src/quant_research_engine/portfolio/full_market_report.py` — `engine_mode` parameter on `build_trades_ledger`, `build_round_trips`, `build_symbol_performance`, `build_full_market_equity_curve`, `build_strategy_performance`, `write_full_market_report`
- `src/quant_research_engine/portfolio/io.py` — `write_full_market_report()` call in `write_shared_cash_result()`; updated `_shared_manifest_role()` and `_shared_report_paths()` for full-market roles
- `tests/test_full_market_report.py` — 6 new test classes (17 tests): `TestBuildTradesLedgerSharedCash`, `TestBuildRoundTripsSharedCash`, `TestBuildSymbolPerformanceSharedCash`, `TestBuildFullMarketEquityCurveSharedCash`, `TestBuildStrategyPerformanceSharedCash`, `TestWriteFullMarketReportSharedCash`
- `tests/test_portfolio_io.py` — 2 new tests: `test_write_shared_cash_result_includes_full_market_files`, `test_shared_cash_manifest_validates_full_market_roles`

## Validation

```bash
uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py -q
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_full_market_report.py tests/test_research_run.py -q
scripts/check-progress-docs.sh
git diff --check
```

## Next Step

Claude Code implements, self-reviews, updates agent docs, then hands off for git finalization.
