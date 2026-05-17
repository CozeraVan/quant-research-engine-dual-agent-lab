# Quant Research Engine Task Plan

## Goal

Move the active project focus from factor repair to `quant-research-engine`, and keep the next work gated on planning before any new engine coding.

`quant_ts` and `indicators_tushare` are treated as upstream production data systems. The current QRE goal is to improve the reusable research and backtesting engine on top of their database outputs.

## Current Phase

Phase 4 first implementation is complete: shared-cash portfolio accounting now uses lot-level FIFO cost basis and T+1 sellable inventory checks for rebalance/exit sells.

## Phases

| Phase | Status | Scope | Exit Criteria |
|---|---|---|---|
| 0. Status correction | complete | Reconcile project docs, QRE completion status, upstream data status, and indicators smoke-write record. | User reviewed corrected plan and approved next-step progress. |
| 1. QRE completion audit | complete | Map implemented modules/tests/CLI to MVP goals and identify gaps. | Current capability matrix is recorded in `findings.md` and module docs. |
| 2. Data preflight design | complete | Define standard preflight checks for market data, factors, universe, and joins before any broad backtest. | `qre preflight` checks market/factor/join/metadata/universe/liquidity/benchmark with smoke/test verification. |
| 3. Evaluation engine next milestone | complete | Add IC, Rank IC, quantile returns, and rough friction-adjusted screening. | IC/Rank IC/quantile/friction-adjusted summaries are implemented and smoke-tested. |
| 4. Portfolio engine next milestone | in_progress | Improve realistic accounting where current MVP is thin, especially sellable inventory/lots and benchmark wiring. | Lot-level FIFO and T+1 sellable inventory are implemented and smoke-tested; benchmark wiring remains. |
| 5. Reporting and reproducibility | pending | Standardize run manifests, validation commands, and report audit flow for research runs. | Reports are discoverable, auditable, and reproducible. |

## Non-Goals For Current Planning Pass

- Do not launch more `indicators_tushare` historical repair jobs.
- Do not add new QRE runtime features before user review.
- Do not reinterpret strategy results as research conclusions; current smokes only validate plumbing.

## Immediate Next Action

Continue Phase 4 with benchmark/index wiring or stronger failed-order diagnostics.
