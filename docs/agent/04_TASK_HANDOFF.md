# Task Handoff

## Current Task

Implement the QRE strategy-entry contract documentation set. The immediate goal is documentation implementation by Claude Code: create clear authoring standards and examples so strategy writing and factor handoff become modular and scalable.

## Task ID

QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001

## Current Status

DONE. Documentation implementation passed Codex review and was finalized locally.

## Current Owner

CODEX

## Completed

- Product boundary clarified:
  - QRE owns strategy input standards, factor availability validation, backtest execution, and report output contracts.
  - QRE does not own rewriting `research-notes` / `strategy-research` or computing indicators internally.
  - `indicators_tushare` remains the upstream technical-indicator calculator and `factors.*` producer.
- Strategy-entry direction clarified:
  - Entry strategy work is documentation-first.
  - QRE should write the MD contract that tells humans, Codex, Claude Code, and external strategy projects how a strategy entry file should be authored.
  - External strategy projects can convert natural-language strategy descriptions into QRE-standard strategy files.
- Report-output direction clarified:
  - The MT5 report sample is the baseline.
  - QRE reports should be full-market outputs, not per-stock report files.
  - Unified transaction tables must include `symbol`.
- Design captured:
  - `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md`
- Full-market report design captured:
  - `docs/superpowers/specs/2026-05-21-full-market-backtest-report-design.md`
- TradingView strategy tester screenshots reviewed:
  - performance summary
  - benchmark comparison
  - risk-adjusted metrics
  - trade analysis
  - capital/margin/run-up/drawdown sections
- Implementation completed:
  - `src/quant_research_engine/portfolio/full_market_report.py` — full-market report builders and entry point (~350 lines)
  - `src/quant_research_engine/portfolio/io.py` — wired `write_full_market_report()` into `write_batch_result()`
  - `src/quant_research_engine/portfolio/report_manifest.py` — 9 new required-column rules
  - `tests/test_full_market_report.py` — 23 tests across 12 test classes
  - `openpyxl>=3.1.0` added to `pyproject.toml`

## Scope Notes

The strategy-entry MD contract is future work and should explain:

- Strategy Card fields.
- Factor Requirements fields.
- Experiment Plan fields.
- Missing-factor request fields for `indicators_tushare`.
- Compiler expectations from standard entry to existing QRE `StrategySpec` / backtest tasks.
- Three-strategy validation requirement:
  - randomly or deliberately select three existing project strategy families,
  - convert them into the standard entry format,
  - keep them clear and readable,
  - compile them into executable current QRE inputs,
  - run a small-scope smoke test with exit code `0`.

The current report-output implementation produces:

- `backtest_report.xlsx` (10 sheets: Overview, Performance, TradesLedger, RoundTrips, SymbolPerformance, EquityCurve, DrawdownCurve, TradeAnalysis, CapitalUsage, Artifacts)
- `trades_ledger.csv`
- `round_trips.csv`
- `symbol_performance.csv`
- `strategy_performance.json`
- `equity_curve.csv`
- `drawdown_curve.csv`
- `trade_analysis.json`
- `capital_usage.json`
- `report_manifest.json` (updated with new stable roles)

Charts are optional in the first implementation. The required acceptance target is stable tables, files, manifest entries, and audit/discovery behavior.

## Residual Limitations

- Commission splits (`commission`, `stamp_tax`, `transfer_fee`, `slippage`) are null in the trades ledger because the current engine does not track per-order cost components separately.
- Margin fields (`average_margin_used`, `max_margin_used`, `min_margin_used`) are null because the current simulation is cash-only.
- Intratrade path fields (`max_favorable_return`, `max_adverse_return`, bars-in-trade stats) are null because the A-share daily engine does not track intra-trade bar-level paths.
- Batch-only for the first release; shared-cash reuse is future work.

## Prior Completed Context

The local browser backtest console is complete and finalized locally in commit `766dc98`. A later local GUI update made the verified EMA200 + Bollinger reversal strategy preload into the editor from `examples/ema200_bollinger_reversal.yaml`; those GUI files are still uncommitted and should not be reverted by this planning task.

## Validation Baseline

Documentation and implementation validation:

```bash
uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
scripts/check-progress-docs.sh
git diff --check
```

Current results: 254 passed, 2 warnings (pre-existing numpy) in 3.20s; all checks pass.

## Known Risks

- Existing report outputs and manifest roles remain compatible.
- First implementation does not have true charts, but workbook sheets and data tables are emitted.
- Current engine does not split every cost component (`commission`, `stamp_tax`, `transfer_fee`, `slippage_amount`); MT5 columns exist with null/zero conventions where source data is unavailable.
- Independent batch mode has no single shared cash account; full-market equity is synthesized by summing per-symbol equity curves.
- QRE must not compute missing indicators internally; it should emit missing-factor requests for `indicators_tushare`.
- Existing uncommitted GUI changes are outside this planning task and must be preserved.

## Next Suggested Step

Proceed to the next strategy-IO slice: factor-missing handoff operational standard and workflow linkage.
