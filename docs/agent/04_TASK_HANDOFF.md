# Task Handoff

## Current Task

Implement the QRE operational missing-factor handoff standard. The immediate goal is to make missing-factor requests durable, machine-readable, and workflow-ready for upstream `indicators_tushare`.

## Task ID

QRE-FACTOR-MISSING-HANDOFF-STANDARD-001

## Current Status

DONE. Implementation passed Codex review and is finalized locally.

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
- Strategy entry standard docs completed: `docs/strategy_entry/` with 6 documentation files.
- Full-market report design and implementation completed:
  - MT5 workbook baseline + TradingView strategy tester metrics unified into QRE batch backtest outputs.
  - `src/quant_research_engine/portfolio/full_market_report.py`, wired into `io.py`, 9 manifest roles, 23 tests.
  - `realized_pnl` semantic fix applied and regression-tested.
- Missing-factor handoff implementation completed:
  - `src/quant_research_engine/strategies/missing_factor.py` — `MissingFactorRequest` model, extraction from `PreflightReport`, JSON emission.
  - `src/quant_research_engine/apps/cli.py` — `qre preflight --output-dir` writes `missing_factor_requests.json`.
  - `tests/test_missing_factor.py` — 25 tests (model, parsing, extraction, emission).
  - `tests/test_cli.py` — 3 CLI tests (output-dir empty, output-dir with missing, no-output-dir stdout).
  - `docs/strategy_entry/missing_factor_request.md` — lifecycle states added.

## Scope Notes

The strategy-entry MD contract is complete under `docs/strategy_entry/`:

- Strategy Card fields (`strategy_card.md`).
- Factor Requirements fields (`factor_requirements.md`).
- Experiment Plan fields (`experiment_plan.md`).
- Missing-factor request fields for `indicators_tushare` (`missing_factor_request.md`).
- Three complete examples: RSI2, EMA200+Bollinger, MACD (`examples.md`).
- README with end-to-end flow and project boundaries (`README.md`).

The current report-output implementation produces:

- `backtest_report.xlsx` (10 sheets: Overview, Performance, TradesLedger, RoundTrips, SymbolPerformance, EquityCurve, DrawdownCurve, TradeAnalysis, CapitalUsage, Artifacts)
- `trades_ledger.csv`, `round_trips.csv`, `symbol_performance.csv`, `strategy_performance.json`, `equity_curve.csv`, `drawdown_curve.csv`, `trade_analysis.json`, `capital_usage.json`
- `report_manifest.json` (updated with new stable roles)

The current missing-factor implementation produces:

- `missing_factor_requests.json` — stable JSON array matching `docs/strategy_entry/missing_factor_request.md` schema.
- Stdout summary: `missing_factor_count`, `missing_factor_status` (ok/pending), per-missing-factor lines.
- Empty `[]` when no factors are missing.

## Residual Limitations

- Commission splits (`commission`, `stamp_tax`, `transfer_fee`, `slippage`) are null in the trades ledger because the current engine does not track per-order cost components separately.
- Margin fields (`average_margin_used`, `max_margin_used`, `min_margin_used`) are null because the current simulation is cash-only.
- Intratrade path fields (`max_favorable_return`, `max_adverse_return`, bars-in-trade stats) are null because the A-share daily engine does not track intra-trade bar-level paths.
- Batch-only for the first release; shared-cash reuse is future work.
- Column name parsing is heuristic; `expected_table` and `expected_column` are the authoritative fields.
- All factors treated as `required: true` — current `StrategySpec` has no optional-factor concept.

## Prior Completed Context

The local browser backtest console is complete and finalized locally in commit `766dc98`. A later local GUI update made the verified EMA200 + Bollinger reversal strategy preload into the editor from `examples/ema200_bollinger_reversal.yaml`; those GUI files are still uncommitted and should not be reverted by this planning task.

## Validation Baseline

Documentation and implementation validation:

```bash
uv run pytest tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py -q
scripts/check-progress-docs.sh
git diff --check
```

Current results: 168 passed, 2 warnings (pre-existing numpy) in 2.01s; all checks pass.

## Known Risks

- Existing report outputs and manifest roles remain compatible.
- First implementation does not have true charts, but workbook sheets and data tables are emitted.
- Current engine does not split every cost component (`commission`, `stamp_tax`, `transfer_fee`, `slippage_amount`); MT5 columns exist with null/zero conventions where source data is unavailable.
- Independent batch mode has no single shared cash account; full-market equity is synthesized by summing per-symbol equity curves.
- QRE must not compute missing indicators internally; it should emit missing-factor requests for `indicators_tushare`.
- Column name parsing from `factor_fields` targets is heuristic and documented as best-effort.
- Existing uncommitted GUI changes are outside this planning task and must be preserved.

## Next Suggested Step

Proceed to next strategy-IO slice: compiler/preflight linkage from high-level strategy entry format to executable current `StrategySpec`.
