# Coding Handoff

## Task ID

QRE-REPORT-MT5-TV-FULL-MARKET-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

FIXED. Codex review found one blocking semantic issue in `realized_pnl` — fixed and resubmitted for re-review.

## Implementation Summary

Implemented the additive full-market report bundle from `docs/agent/08_IMPLEMENTATION_BRIEF.md`, combining the MT5 workbook baseline and TradingView strategy tester metrics into QRE batch backtest outputs:

- **new module `full_market_report.py`** (`src/quant_research_engine/portfolio/full_market_report.py`, ~350 lines): build functions for every report artifact plus the main `write_full_market_report()` entry point. The module keeps report-building logic separate from the 685-line `io.py`.
  - `build_trades_ledger()` — combines per-symbol `orders` DataFrames into a unified ledger with MT5 columns (`lot_count`, `commission`, `stamp_tax`, `transfer_fee`, `slippage_amount`, `realized_pnl`, `cash_after`, `position_after`, `order_reason`, `status`), filling unavailable cost-split columns with `NaN`/null.
  - `build_round_trips()` — combines per-symbol `trades` DataFrames, derives `holding_days`, `entry_notional`, `exit_notional`, `gross_return`, `net_return` from price×quantity and P&L.
  - `build_symbol_performance()` — enriches the batch `summary` DataFrame with per-symbol Sharpe and max drawdown via `summarize_equity_curve()`.
  - `build_full_market_equity_curve()` — aligns dates across all symbols and sums `total_equity` directly; computes `daily_return`, `cumulative_return`, `position_count`.
  - `build_drawdown_curve()` — derives `running_peak`, `drawdown`, `drawdown_pct`, `drawdown_duration_days` from the full-market equity curve.
  - `build_strategy_performance()` — aggregates win/loss counts, `win_rate`, `profit_factor`, `expectancy`, Sharpe, Sortino, max consecutive wins/losses, best/worst symbols into a JSON-ready dict.
  - `build_trade_analysis()` — P&L distribution bins via numpy histogram, win/loss breakdown, outlier detection (3-sigma), per-pair summary.
  - `build_capital_usage()` — CAGR from equity curve growth, margin fields null for cash-only simulation.
  - `write_full_market_excel()` — writes `backtest_report.xlsx` with 10 sheets (Overview, Performance, TradesLedger, RoundTrips, SymbolPerformance, EquityCurve, DrawdownCurve, TradeAnalysis, CapitalUsage, Artifacts) using openpyxl with bold headers.
  - `write_full_market_report()` — main entry point: calls all builders, writes 9 artifact files, returns a paths dict.

- **Wired into `write_batch_result()`** (`src/quant_research_engine/portfolio/io.py`): the `write_full_market_report()` call happens after per-symbol directory writing but before manifest generation. New artifact paths are merged into the existing paths dict. Updated `_batch_manifest_role()` to map report keys to stable manifest roles, and `_batch_report_paths()` to list all new artifacts.

- **Manifest roles added** (`src/quant_research_engine/portfolio/report_manifest.py`): 9 new entries in `_REQUIRED_COLUMNS_BY_ROLE` — `trades_ledger`, `round_trips`, `symbol_performance`, `full_market_equity_curve`, `drawdown_curve`, `full_market_report_workbook`, `strategy_performance`, `trade_analysis`, `capital_usage`.

- **Tests** (`tests/test_full_market_report.py`, new, 23 tests): 12 test classes covering every builder function, Excel workbook creation (sheet names and structure verified), integration with `write_batch_result()`, manifest role registration, manifest validation, and empty-result edge cases.

## Files Changed

- `pyproject.toml` — added `openpyxl>=3.1.0` dependency
- `src/quant_research_engine/portfolio/full_market_report.py` — new
- `src/quant_research_engine/portfolio/io.py` — wired full-market report into `write_batch_result()`
- `src/quant_research_engine/portfolio/report_manifest.py` — added 9 new required-column rules
- `tests/test_full_market_report.py` — new (23 tests)
- `docs/agent/04_TASK_HANDOFF.md` — updated status/owner/phase
- `docs/agent/05_PROGRESS.md` — updated phase/task entry/verified state
- `docs/agent/09_CODING_HANDOFF.md` — this file
- `docs/agent/11_AGENT_STATE.md` — phase to CODEX_REVIEWING, owner to CODEX
- `docs/agent/12_AGENT_BOARD.md` — message/recipient/next step updated

## Validation Results

- `uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q` → 254 passed, 2 warnings (pre-existing numpy) in 3.14s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Residual Limitations

- **Unavailable cost splits**: the current engine does not track per-order `commission`, `stamp_tax`, `transfer_fee`, or `slippage` separately. Those MT5 columns exist in `trades_ledger` as `None`/`NaN` with stable column names.
- **Margin fields**: `average_margin_used`, `max_margin_used`, `min_margin_used` are `None` because the current simulation is cash-only (no leverage).
- **Intratrade path**: `max_favorable_return`, `max_adverse_return`, and bars-in-trade statistics are `None` because the current A-share daily engine does not track intra-trade bar-level paths.
- **Charts**: the Excel workbook contains data sheets only; no rendered charts in this first implementation.
- **Batch-first**: only batch mode writes full-market reports. Shared-cash reuse is noted as future work.

## Constraints

- No existing report outputs renamed or removed.
- No changes to engine contracts, market profiles, single-symbol, batch, or shared-cash logic.
- `docs/legacy/**` untouched.
- Read-only data access preserved.

## Fixes Applied (Re-review Cycle)

1. **realized_pnl semantics** — `build_trades_ledger()` line 81: changed `"realized_pnl": None if side == "buy" else _safe_float(record.get("cost"))` to `"realized_pnl": None`. The `cost` field is a transaction fee, not realized P&L. Sell rows now have `None` for `realized_pnl` (same as buy rows), since the current engine does not track realized P&L at the individual order level. Added assertion in `test_sell_rows_have_null_realized_pnl` that sell-row `realized_pnl` is `NaN` and not equal to `total_cost`.

## Git State

- Branch: `master`
- Last accepted implementation commit: `766dc98`, `Make backtest iteration directly usable in a local browser console`
- Working tree contains all full-market report implementation files, tests, and agent doc updates.

## Next Suggested Step

Codex reviews the implementation, runs validation, and writes `docs/agent/10_REVIEW_REPORT.md`.
