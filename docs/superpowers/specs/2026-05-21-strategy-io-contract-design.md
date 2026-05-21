# QRE Strategy IO Contract Design

Date: 2026-05-21

## Purpose

QRE should become the standard contract, validation, backtest, and reporting layer for daily A-share technical strategy research.

The engine should not own the external strategy libraries. It should define how a strategy must enter QRE, how QRE checks factor availability, how it compiles accepted strategy inputs into current backtest tasks, and how it emits full-market reports after a run.

The long-term workflow is:

```text
write strategy -> check factor library -> backtest -> evaluate alpha
```

Expanded across projects:

```text
research-notes / strategy-research
  natural-language or classic strategy descriptions
  -> QRE-standard strategy input file

QRE
  validate strategy input
  -> resolve factor requirements against factors.*
  -> emit factor gaps if needed
  -> compile to backtest tasks
  -> run full A-share backtests
  -> emit standard reports

indicators_tushare
  consume missing-factor requests
  -> compute/backfill missing indicators or periods
  -> write factors.* tables
```

## Project Boundaries

QRE owns:

- the strategy input writing standard
- factor requirement declarations
- factor availability checks
- missing-factor request output
- compilation from standard strategy input into current QRE strategy specs
- full-market backtest execution
- standardized report artifacts
- GUI visualization of this contract

QRE does not own:

- collecting or rewriting all classic strategy prose
- modifying `research-notes` or `strategy-research`
- computing technical indicators internally
- writing upstream market/factor tables during preflight, evaluation, or backtest
- deciding which external strategy ideas should exist

`research-notes` and `strategy-research` own strategy knowledge and source material. They may read this document and generate QRE-standard strategy entry files.

`indicators_tushare` owns technical indicator calculation, period expansion, backfill, and persistence into `factors.*`.

## First Scope

Version 1 focuses on daily A-share technical-indicator strategies.

Supported source data:

- market bars from `public.stock_daily`
- technical indicator columns from `factors.*`
- optional metadata from QRE metadata adapters when available

Out of scope for this first standard:

- minute bars
- tick data
- live trading
- fundamental strategies
- machine-learning model training
- clustering-driven strategy discovery
- QRE-side indicator calculation

Those can be added later after the daily technical strategy contract is stable.

## Strategy Entry Standard

The strategy input should tell QRE what the strategy means at the research-contract level. It should not force the author to hand-write low-level database targets such as `factors.stock_daily_momentum_close.rsi_2`.

The input standard has three conceptual parts.

### Strategy Card

The strategy card describes the strategy identity and trading logic.

Required content:

- `strategy_id`
- `name`
- `family`
- `description`
- `direction`
- `entry_rules`
- `exit_rules`
- `risk_controls`
- `holding_rules`
- `execution_assumptions`

Example shape:

```yaml
strategy:
  id: rsi2_oversold_reversal
  name: RSI2 Oversold Reversal
  family: mean_reversion
  description: Buy short-term RSI oversold signals and exit on RSI recovery.
  direction: long_only

rules:
  entry:
    all:
      - indicator: rsi
        alias: rsi_fast
        operator: "<"
        value: 10
  exit:
    any:
      - indicator: rsi
        alias: rsi_fast
        operator: ">"
        value: 70
```

### Factor Requirements

Factor requirements describe what data the strategy needs. They are the handoff between QRE and `indicators_tushare`.

Required content:

- indicator name
- source price field
- period/window
- extra parameters
- alias used by rules
- required/optional flag
- reason

Example shape:

```yaml
factor_requirements:
  - alias: rsi_fast
    indicator: rsi
    source: close
    period: 2
    required: true
    reason: entry and exit threshold signal
```

For multi-output indicators, each output must be explicit enough for QRE to map aliases to columns:

```yaml
factor_requirements:
  - alias: macd_line
    indicator: macd
    source: close
    params:
      fast: 12
      slow: 26
      signal: 9
    output: macd
    required: true
  - alias: macd_signal
    indicator: macd
    source: close
    params:
      fast: 12
      slow: 26
      signal: 9
    output: signal
    required: true
```

### Experiment Plan

The experiment plan describes how to run and compare the strategy.

Required content:

- universe
- date range
- initial capital
- market profile
- execution mode
- cost/slippage assumptions
- grouping fields
- output directory

Example shape:

```yaml
experiment:
  id: rsi2_oversold_reversal_smoke
  frequency: daily
  market: ashare
  start: 2020-01-01
  end: 2024-12-31

universe:
  include: all_a
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120

execution:
  signal_date: t
  entry_execution: t_plus_1_open
  exit_execution: t_plus_1_open
  market_profile: ashare_daily_default

risk:
  max_holding_days: 5
  stop_loss_pct: 0.20
  trailing_stop_pct: null
  take_profit_pct: null
```

## Factor Availability Contract

QRE should validate factor requirements before a broad backtest.

The validation flow is:

1. Read the standard strategy input.
2. Extract `factor_requirements`.
3. Resolve each requirement against the QRE factor catalog and PostgreSQL `factors.*`.
4. Report available factors and columns.
5. Emit a missing-factor request for unavailable requirements.

Missing-factor requests should be machine-readable and include:

- strategy id
- requirement alias
- indicator name
- category if known
- source price field
- period/window
- extra parameters
- output name
- expected table/column convention when known
- requested date range
- reason

QRE should not compute the missing factor. It should tell `indicators_tushare` what is missing.

## Compiler Contract

The standard entry file is for people and upstream strategy generators.

The compiler output is for QRE internals. It can remain compatible with the current `StrategySpec` until a fuller internal model is needed.

The compiler should:

- map aliases to resolved factor table/column targets
- translate rule blocks into safe QRE signal expressions
- preserve strategy metadata in run manifests and reports
- fail early with clear messages when factor requirements cannot be resolved

The author of the standard entry file should not need to know current table names.

## Three-Strategy Validation Step

Before implementation is considered accepted, QRE should validate the contract with three existing strategy families from project material.

Recommended examples:

- RSI2 oversold reversal
- EMA200 plus Bollinger-band mean reversion
- MACD zero-axis momentum or Donchian channel breakout

Acceptance for this validation step:

- each strategy is written in the standard entry format
- each file is readable and easy to understand
- each file declares factor requirements without low-level table paths
- each file can be compiled into the current executable QRE strategy spec
- each file can run a small-scope smoke test
- the smoke test exits with status code `0`

Small-scope smoke tests are plumbing checks only. They must not be documented as strategy alpha evidence.

## Full-Market Report Output Standard

QRE reports should use the provided MT5 Excel report as the baseline, then add A-share research fields.

The report is not split by stock. Full A-share runs should produce one unified report set, with `symbol` included in transaction and performance tables.

The combined MT5 + TradingView report contract is defined in:

- `docs/superpowers/specs/2026-05-21-full-market-backtest-report-design.md`

Required artifacts:

- `backtest_report.xlsx`
- `trades_ledger.csv`
- `round_trips.csv`
- `symbol_performance.csv`
- `strategy_performance.json`
- `equity_curve.csv`
- `drawdown_curve.csv`
- `report_manifest.json`

### Trades Ledger

`trades_ledger.csv` records every buy/sell execution across all symbols.

Required columns:

- `run_id`
- `strategy_id`
- `symbol`
- `trade_date`
- `side`
- `quantity`
- `lot_count`
- `price`
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

`realized_pnl` is expected on sell rows. Buy rows may leave it null.

### Round Trips

`round_trips.csv` records one completed entry-to-exit trade cycle per row.

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

### Symbol Performance

`symbol_performance.csv` records one row per stock.

Required columns:

- `symbol`
- `trade_count`
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
- `information_ratio_vs_buy_hold`
- `max_drawdown`
- `turnover`
- `total_cost`
- `failed_order_count`

### Strategy Performance

`strategy_performance.json` records full-market summary metrics.

Required fields:

- strategy id/name/family/description
- date range
- universe definition
- indicator requirements and parameter snapshot
- `symbol_count`
- `traded_symbol_count`
- `total_trade_count`
- `win_rate`
- `profit_factor`
- `expectancy`
- `gross_profit`
- `gross_loss`
- `net_profit`
- `positive_symbol_rate`
- `mean_symbol_return`
- `median_symbol_return`
- `portfolio_total_return`
- `sharpe`
- `information_ratio`
- `max_drawdown`
- `total_cost`
- `best_symbols`
- `worst_symbols`

## GUI Role

The GUI is a visualization and parameter editing layer.

It should eventually render the strategy entry contract as:

- strategy family selector
- indicator selector
- period/window selector
- entry/exit/risk controls
- universe/date/execution controls
- factor availability status
- missing-factor request viewer
- run status and report viewer

The GUI should not become the owner of strategy semantics.

## Implementation Order

Recommended sequence:

1. Document and accept this contract.
2. Add report-output contract support, because current QRE already has orders, trades, summaries, equity curves, and manifests.
3. Add strategy-entry documentation examples and compiler/preflight support.
4. Validate with three existing strategy families and small-scope smoke tests.
5. Connect GUI forms to the standard entry contract.

## Stop Conditions

Do not start code implementation until:

- this strategy IO contract is accepted
- the first implementation slice is explicitly scoped
- the expected output files and validation commands are written into an implementation brief
