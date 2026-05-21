# Full-Market Backtest Report Design

Date: 2026-05-21

## Purpose

QRE full-market backtests need a research-facing report contract, not only engineering CSV/JSON artifacts.

The report must combine:

- the MT5 workbook structure supplied in `ReportHistory-60001281.xlsx`
- the TradingView strategy tester screenshots under `/mnt/hgfs/Ubuntu互传/pics`
- QRE-specific A-share fields such as `symbol`, board/industry metadata, costs, slippage, T+1/limit/suspension failures, and buy-and-hold comparison

The report is for full-market A-share strategy research. It must not create one report per stock. All transaction-level tables include `symbol`.

## Source Templates Reviewed

### MT5 Workbook Baseline

The MT5 workbook contains:

- report header: name, account, broker, date
- positions: open time, position id, symbol, side, volume, open price, stop loss, take profit, close time, close price, commission, swap, profit
- orders: open time, order id, symbol, type, volume, price, stop loss, take profit, filled time, status, comments
- deals: deal time, deal id, symbol, type, in/out direction, volume, price, order id, commission, swap, profit, balance, comments
- open positions and floating P/L
- account state: balance, floating P/L, equity, margin, free margin, margin level
- results: net profit, gross profit, gross loss, profit factor, expected payoff, recovery factor, Sharpe ratio, drawdown, trade counts, win/loss counts, largest/average winning and losing trades, consecutive wins/losses

### TradingView Strategy Tester Baseline

The TradingView screenshots add these report sections:

- equity / buy-and-hold / drawdown chart inputs
- performance return table with all/long/short columns
- profit structure chart
- benchmark comparison:
  - buy-and-hold return
  - buy-and-hold annualized return
  - strategy underperformance/outperformance
- risk-adjusted performance:
  - Sharpe ratio
  - Sortino ratio
- trade analysis:
  - P&L distribution
  - win/loss ratio
  - total trades
  - open trades
  - winning trades
  - losing trades
  - percent profitable
  - average P&L
  - average winning trade
  - average losing trade
  - average win / average loss ratio
  - largest winning trade
  - largest losing trade
  - largest trade percentages
  - outliers and outlier P&L
  - average bars in trade
  - average bars in winning trades
  - average bars in losing trades
- capital usage:
  - CAGR
  - initial capital return
  - required account size
  - account-size return
  - net profit as percentage of max loss
- margin usage:
  - average margin used
  - maximum margin used
  - margin efficiency
  - margin calls
- run-up:
  - average run-up duration
  - average net run-up
  - maximum net run-up
  - maximum run-up intrabar
  - run-up relative to initial capital
- drawdown:
  - average drawdown duration
  - average net drawdown
  - maximum net drawdown
  - maximum drawdown intrabar
  - drawdown relative to initial capital

## Required Output Bundle

A full-market report directory should include:

- `backtest_report.xlsx`
- `trades_ledger.csv`
- `round_trips.csv`
- `symbol_performance.csv`
- `strategy_performance.json`
- `equity_curve.csv`
- `drawdown_curve.csv`
- `trade_analysis.json`
- `capital_usage.json`
- `report_manifest.json`

Existing QRE outputs should remain intact. These files are additive and must not break current `summary.csv`, `summary.json`, `orders.csv`, `trades.csv`, `failed_orders.csv`, window summaries, rolling summaries, or report discovery/audit behavior.

## Excel Workbook Sheets

`backtest_report.xlsx` should contain these sheets in order:

1. `Overview`
2. `Performance`
3. `TradesLedger`
4. `RoundTrips`
5. `SymbolPerformance`
6. `EquityCurve`
7. `DrawdownCurve`
8. `TradeAnalysis`
9. `CapitalUsage`
10. `Artifacts`

Charts are optional in the first implementation. The required contract is the workbook structure and data tables.

## Overview Sheet

Purpose: equivalent to MT5 report header plus QRE strategy metadata.

Required fields:

- `run_id`
- `strategy_id`
- `strategy_name`
- `strategy_family`
- `strategy_description`
- `engine_mode`
- `date_start`
- `date_end`
- `market`
- `frequency`
- `universe`
- `symbol_count`
- `traded_symbol_count`
- `initial_cash`
- `market_profile`
- `entry_execution`
- `exit_execution`
- `cost_model`
- `slippage_model`
- `factor_requirements`
- `strategy_source_path`
- `generated_at`

## Trades Ledger

`trades_ledger.csv` records every buy/sell execution across all symbols.

Required columns:

- `run_id`
- `strategy_id`
- `symbol`
- `trade_date`
- `side`
- `quantity`
- `lot_count`
- `price_raw`
- `price_executed`
- `notional`
- `commission`
- `stamp_tax`
- `transfer_fee`
- `slippage_amount`
- `total_cost`
- `realized_pnl`
- `cash_after`
- `position_after`
- `order_reason`
- `status`

Rules:

- `symbol` is mandatory.
- buy and sell rows stay in the same table.
- `realized_pnl` is expected for sell rows and may be null for buy rows.
- if current engine data cannot split `commission`, `stamp_tax`, `transfer_fee`, or `slippage_amount`, the first implementation should still include the columns and populate known values conservatively.

## Round Trips

`round_trips.csv` records one completed entry-to-exit cycle per row.

Required columns:

- `run_id`
- `strategy_id`
- `symbol`
- `entry_date`
- `exit_date`
- `holding_days`
- `entry_price`
- `exit_price`
- `quantity`
- `entry_notional`
- `exit_notional`
- `gross_pnl`
- `net_pnl`
- `gross_return`
- `net_return`
- `total_cost`
- `exit_reason`
- `max_favorable_return`
- `max_adverse_return`

Rules:

- this table is the canonical source for win rate, profit factor, average win/loss, largest win/loss, and bars-in-trade style metrics
- first implementation may leave max favorable/adverse values null if intratrade path is unavailable, but the columns must exist

## Symbol Performance

`symbol_performance.csv` records one row per stock.

Required columns:

- `symbol`
- `board`
- `industry`
- `trade_count`
- `open_trade_count`
- `win_count`
- `loss_count`
- `win_rate`
- `gross_profit`
- `gross_loss`
- `net_profit`
- `profit_factor`
- `expectancy`
- `strategy_total_return`
- `buy_hold_return`
- `excess_return_vs_buy_hold`
- `sharpe`
- `sortino`
- `information_ratio_vs_buy_hold`
- `max_drawdown`
- `turnover`
- `total_cost`
- `failed_order_count`

Rules:

- `board` and `industry` are included when available and null otherwise
- buy-and-hold comparison should use the same available start/end window for that symbol
- small-scope smoke results are plumbing checks only, not alpha conclusions

## Strategy Performance

`strategy_performance.json` records the full-market summary.

Required fields:

- `run_id`
- `strategy_id`
- `strategy_name`
- `strategy_family`
- `date_start`
- `date_end`
- `symbol_count`
- `traded_symbol_count`
- `total_trade_count`
- `open_trade_count`
- `winning_trade_count`
- `losing_trade_count`
- `win_rate`
- `gross_profit`
- `gross_loss`
- `net_profit`
- `profit_factor`
- `expectancy`
- `recovery_factor`
- `sharpe`
- `sortino`
- `information_ratio`
- `strategy_total_return`
- `buy_hold_return`
- `excess_return_vs_buy_hold`
- `positive_symbol_rate`
- `mean_symbol_return`
- `median_symbol_return`
- `max_drawdown`
- `max_drawdown_duration_days`
- `total_cost`
- `largest_winning_trade`
- `largest_losing_trade`
- `average_winning_trade`
- `average_losing_trade`
- `average_win_loss_ratio`
- `max_consecutive_wins`
- `max_consecutive_losses`
- `average_bars_in_trade`
- `average_bars_in_winning_trades`
- `average_bars_in_losing_trades`
- `best_symbols`
- `worst_symbols`

## Equity And Drawdown Curves

`equity_curve.csv` should contain:

- `trade_date`
- `cash`
- `market_value`
- `total_equity`
- `daily_return`
- `cumulative_return`
- `position_count`
- `turnover`

`drawdown_curve.csv` should contain:

- `trade_date`
- `total_equity`
- `running_peak`
- `drawdown`
- `drawdown_pct`
- `drawdown_duration_days`

For independent batch backtests, QRE may synthesize full-market equity by summing per-symbol equity curves. For shared-cash backtests, the existing portfolio equity curve is the natural source.

## Trade Analysis

`trade_analysis.json` stores TradingView-style analysis fields:

- `pnl_distribution_bins`
- `win_loss_counts`
- `percent_profitable`
- `average_pnl`
- `average_winning_trade`
- `average_losing_trade`
- `average_win_loss_ratio`
- `largest_winning_trade`
- `largest_losing_trade`
- `outlier_count`
- `outlier_pnl`
- `average_bars_in_trade`
- `average_bars_in_winning_trades`
- `average_bars_in_losing_trades`

The first implementation may store histogram data as arrays of bin labels/counts instead of rendering charts.

## Capital Usage

`capital_usage.json` stores TradingView-style capital and margin fields:

- `cagr`
- `initial_capital_return`
- `required_account_size`
- `account_size_return`
- `net_profit_as_pct_of_max_loss`
- `average_margin_used`
- `maximum_margin_used`
- `margin_efficiency`
- `margin_call_count`

QRE daily A-share backtests may not use margin in v1. In that case, margin fields must still exist and be null or zero with a documented convention.

## Report Manifest

`report_manifest.json` must include entries for all new artifacts with stable roles:

- `full_market_report_workbook`
- `trades_ledger`
- `round_trips`
- `symbol_performance`
- `strategy_performance`
- `full_market_equity_curve`
- `drawdown_curve`
- `trade_analysis`
- `capital_usage`

Existing `report-files` and `report-audit` must continue to work.

## Acceptance Evidence

The implementation must include tests proving:

- full-market report files are written for at least batch results
- shared-cash results either write the same contract or clearly share the same writer path
- required CSV/JSON columns exist
- `backtest_report.xlsx` is created
- new files are present in `report_manifest.json`
- `report-files` can discover the new roles
- `report-audit --validate-contents` passes for a generated report
- existing report artifacts and tests remain compatible
