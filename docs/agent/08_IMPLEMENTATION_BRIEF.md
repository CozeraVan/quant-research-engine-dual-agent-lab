# Implementation Brief

## Task ID

QRE-REPORT-MT5-TV-FULL-MARKET-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Current Brief Type

Implementation brief. Implement code, tests, and required documentation updates.

## Background

The user wants QRE to become the stable backtest/reporting engine for future A-share factor and strategy research. The current outputs are useful engineering artifacts, but the research-facing report is still too thin.

Codex reviewed two source templates:

- MT5 workbook: `/mnt/hgfs/Ubuntu互传/research-notes/ReportHistory-60001281.xlsx`
- TradingView strategy tester screenshots: `/mnt/hgfs/Ubuntu互传/pics/1.png` through `/mnt/hgfs/Ubuntu互传/pics/5.png`

The implementation should combine both templates into QRE's full-market report output. QRE backtests normally cover thousands of A-share symbols, so reports must be full-market artifacts with `symbol` columns, not one workbook per stock.

## Canonical Design Source

- `docs/superpowers/specs/2026-05-21-full-market-backtest-report-design.md`

Related but separate strategy-entry design:

- `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md`

Do not implement the strategy-entry compiler in this task.

## Goal

Add an additive full-market report bundle to QRE backtest outputs, at minimum for independent batch backtests, and share the writer with shared-cash outputs where practical.

Required bundle:

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

Existing report outputs must remain intact and compatible.

## Required Workbook Sheets

`backtest_report.xlsx` must contain these sheets in order:

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

Charts are optional in this first implementation. Stable data tables are required.

## Required Artifact Shape

Follow the required columns and fields in `docs/superpowers/specs/2026-05-21-full-market-backtest-report-design.md`.

Important roles for manifest entries:

- `full_market_report_workbook`
- `trades_ledger`
- `round_trips`
- `symbol_performance`
- `strategy_performance`
- `full_market_equity_curve`
- `drawdown_curve`
- `trade_analysis`
- `capital_usage`

If an existing role such as `equity_curve` is still needed for compatibility, keep it. Do not remove existing roles.

## Suggested Implementation Surface

Likely files to inspect and update:

- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/analytics.py`
- `src/quant_research_engine/portfolio/risk.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_io.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `pyproject.toml` only if an explicit Excel writer dependency is required

Use the existing portfolio result objects and output patterns before adding new abstractions.

## Implementation Guidance

- Batch mode:
  - Build a root-level full-market report bundle from `BatchBacktestResult`.
  - Synthesize full-market equity by summing per-symbol equity curves when no true shared-cash account exists.
  - Preserve all per-symbol output directories and existing root summary outputs.

- Shared-cash mode:
  - Reuse the same report writer if practical.
  - If a complete shared-cash bundle is too broad, document the limitation in `09_CODING_HANDOFF.md` and keep batch fully implemented.

- Transaction ledger:
  - Include both buy and sell executions in one table.
  - `symbol` is mandatory.
  - If current order/trade data cannot split `commission`, `stamp_tax`, `transfer_fee`, or `slippage_amount`, include the columns and populate known values conservatively with a documented null/zero convention.

- Round trips:
  - Prefer existing realized trade records where they represent completed entry-to-exit cycles.
  - Keep `symbol`, entry/exit timestamps, quantity, prices, gross/net P&L, returns, cost, and exit reason columns stable.

- Symbol performance:
  - Produce one row per stock.
  - Include buy-and-hold comparison over the same available date window where possible.
  - Include board/industry when available; otherwise use nulls.

- Strategy performance:
  - Aggregate all-market totals, profitability metrics, Sharpe/Sortino/IR when computable, drawdown, cost, best/worst symbols, and win/loss metrics.

- Drawdown/trade/capital analysis:
  - Compute fields that are available from daily equity/trade data.
  - Keep margin fields present and null/zero for current cash-only A-share flows.

## Non-Goals

- Do not implement the standard strategy-entry compiler in this task.
- Do not rewrite `research-notes`, `strategy-research`, or `indicators_tushare`.
- Do not compute missing technical indicators inside QRE.
- Do not add database writes.
- Do not remove or rename existing report files unless required by a failing compatibility test.
- Do not present small-scope smoke output as alpha or strategy-quality evidence.

## Acceptance Criteria

- [ ] Batch backtest output writes the required full-market report files.
- [ ] `backtest_report.xlsx` is created with all required sheets.
- [ ] Required CSV and JSON columns/fields exist.
- [ ] New artifacts are recorded in `report_manifest.json` with stable roles.
- [ ] `qre report-files` can discover the new roles.
- [ ] `qre report-audit --validate-contents` passes for a generated report.
- [ ] Existing portfolio report files and existing manifest/audit tests remain compatible.
- [ ] Any unavailable MT5/TradingView fields are still represented with documented null/zero conventions.
- [ ] `docs/agent/09_CODING_HANDOFF.md` records changed files, validation evidence, and residual limitations.

## Validation Commands

Run at minimum:

```bash
uv run pytest tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
scripts/check-progress-docs.sh
git diff --check
```

If a new Excel dependency is added, also run the smallest test that proves the workbook can be opened and sheet names can be inspected.

## Risks

- The environment may not already include an Excel writer/reader dependency. Add the lightest explicit dependency only if needed.
- Batch mode does not represent a true shared-cash portfolio. The synthesized full-market equity curve must be documented as an aggregate of per-symbol curves.
- Current engine cost records may not decompose every fee component. Do not fake unavailable splits; keep columns stable and document conventions.
- Some TradingView chart-style fields may be table-only in v1. That is acceptable if the data is present.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
