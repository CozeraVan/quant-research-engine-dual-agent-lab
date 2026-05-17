# MVP Plan

> Archived Note:
> This document was created before the dual-agent workflow migration.
> Current authoritative planning, progress, handoff, and review documents live in docs/agent/.
> Keep this file for historical reference only.

## Status Corrected On 2026-05-17

The original MVP plan below was written before the current engine implementation matured. As of the latest inspection:

- `quant_ts` and `indicators_tushare` are upstream production data systems.
- `indicators_tushare` is treated as repaired and in daily-update mode.
- Active development focus is now `quant-research-engine`.
- QRE full test suite currently passes: `156 passed`.
- Fresh read-only QRE DB/factor/evaluation smokes worked for `2026-05-11` to `2026-05-15`.

## Corrected Milestone Status

| Milestone | Current Status | Notes |
|---|---|---|
| 1. Documentation and project skeleton | complete | Project structure, docs, configs, examples, and module boundaries exist. |
| 2. Core interfaces | complete for MVP | Core models, strategy specs, market profile interfaces, and request/result models exist. |
| 3. A-share daily data adapter | complete for MVP | PostgreSQL market/factor loading, metadata fallback, benchmark skeleton, smoke CLI, and read-only preflight CLI with universe/liquidity diagnostics exist. |
| 4. Large evaluation engine MVP | complete for MVP | Expression signal event study, forward returns, IC, Rank IC, quantile returns, and rough friction-adjusted screening exist. |
| 5. Detailed portfolio engine MVP | advanced MVP | Single-symbol, independent batch, and shared-cash portfolio backtests exist with A-share market profile, costs, slippage, risk controls, rebalance, lot-level FIFO accounting, T+1 sellable inventory checks, reports, and manifests. Thin areas remain around real index benchmark wiring. |
| 6. Reporting | advanced MVP | CSV/JSON/Markdown reports, report manifests, report discovery, content validation, and audit CLI exist. |

## Next Approved Workstream After User Review

Do not start feature coding until the corrected plan is approved. The next implementation workstream should be:

1. Tighten the portfolio engine:
   - benchmark/index wiring,
   - stronger failed-order diagnostics,
   - reproducible run manifests for larger research jobs.

## Historical Plan

### Milestone 1: Documentation and Project Skeleton

Goal:

- Create the project.
- Capture design decisions.
- Define module boundaries.
- Do not implement engine code yet.

Status: complete.

### Milestone 2: Core Interfaces

Implement minimal reusable interfaces:

- instrument model
- bar model
- factor frame model
- market profile interface
- strategy specification interface
- evaluation request/result models
- portfolio request/result models

Success criteria:

- Interfaces do not hardcode A-share or daily-only assumptions.
- A-share daily can be implemented as the first concrete profile.

### Milestone 3: A-Share Daily Data Adapter

Implement read-only PostgreSQL adapter for:

- `public.stock_daily`
- `factors.*`
- benchmark data if available
- metadata if available

Success criteria:

- Small smoke query works for a few stocks and a short date range.
- Factor availability check reports missing/non-null coverage.

### Milestone 4: Large Evaluation Engine MVP

Implement fast full-market screening:

- expression signal
- forward returns
- simple friction adjustment
- IC / Rank IC
- quantile return
- industry/board/time-window/regime summaries where metadata exists

Success criteria:

- Run one simple factor test across a small stock subset.
- Run the same test across full A-share daily data after smoke validation.

### Milestone 5: Detailed Portfolio Engine MVP

Implement simple account-level simulation:

- long-only
- equal weight top-N or boolean signal entries
- t signal and t+1 open execution
- T+1 sellability
- price-limit and suspension checks
- commission, stamp tax, transfer fee, slippage
- cash, positions, sellable inventory
- equity curve

Success criteria:

- One simple A-share daily strategy produces orders, fills, positions, equity curve, and risk summary.

### Milestone 6: Reporting

Generate standardized outputs:

- `orders.csv`
- `fills.csv`
- `trades.csv`
- `positions.csv`
- `equity_curve.csv`
- `factor_summary.csv`
- `risk_summary.csv`
- `benchmark_comparison.csv`
- Markdown report

Success criteria:

- One experiment can be reproduced from saved config and output metadata.

### First Candidate Strategy for Validation

RSI(2) reversal:

- universe: A-share, excluding ST, suspended, newly listed, and low-liquidity stocks
- signal: `rsi_2 < 10`
- execution: next trading day open
- exit: hold 5 trading days or `rsi_2 > 70`
- market profile: A-share daily default
- benchmark: broad-market index or full-A equal-weight proxy

Reason:

This strategy is simple enough to validate the whole pipeline while still using a real technical factor and realistic trading constraints.
