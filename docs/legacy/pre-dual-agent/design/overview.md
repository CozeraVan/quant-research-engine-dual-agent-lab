# Design Overview

## Summary

`quant-research-engine` is a general research and backtesting framework. It should borrow the usability strengths of MQL5, TradingView, and Backtrader while adding full-market batch research and realistic market-specific rules.

The first concrete use case is A-share daily technical-factor research.

## Why This Project Exists

Existing tools are useful for single-symbol backtests, but this project needs to answer broader research questions:

- Which technical factors are effective in A-share data?
- Which factor combinations are stable?
- Which strategy families work across market regimes?
- Which stocks, industries, boards, liquidity groups, and market-cap groups respond best?
- Does an apparent edge survive costs, slippage, price limits, suspensions, and T+1?
- How does a strategy compare with benchmarks and random baselines?

## Two-Engine Design

### Evaluation Engine

The evaluation engine is the large, fast screening engine.

It should evaluate factors, factor combinations, and strategy expressions across the full market. It is not a full account simulator, but it should include rough trading friction so obviously fragile signals can be filtered out early.

Expected outputs:

- forward returns
- IC and Rank IC
- quantile returns
- top-minus-bottom spreads
- factor decay
- regime summaries
- industry/board/market-cap/liquidity comparisons
- benchmark and random-baseline comparison
- clustering-ready result tables

### Portfolio Engine

The portfolio engine is the detailed validation engine.

It should simulate account-level trading with realistic market rules and accounting. It is used after the evaluation engine finds promising candidates.

Expected outputs:

- orders
- fills
- failed orders and reasons
- trades
- positions
- cash ledger
- daily equity curve
- drawdown curve
- risk and return metrics
- benchmark comparison

## Strategic Direction

The project should be built as a universal engine with market plugins.

The core framework must define common interfaces for instruments, time, data, signals, orders, fills, accounts, analytics, and reports. A-share rules should be implemented as the first market profile, not as assumptions hidden inside the core engine.

## First-Milestone Boundary

The first milestone should not try to implement every future market.

It should implement the universal interfaces only where needed, then provide one complete market implementation:

- A-share
- daily bars
- technical factors
- long-only
- t signal, t+1 execution
- full-market evaluation
- simplified but realistic portfolio backtest
