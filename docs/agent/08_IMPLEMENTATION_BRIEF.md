# Implementation Brief

## Task ID

QRE-PORTFOLIO-BASELINE-COMPARISON-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Populate the portfolio reporting baseline so strategy results can be compared against hold-to-maturity and, when benchmark context is available, against benchmark performance. Keep industry metadata passthrough intact so same-industry comparisons remain available through the existing summary/grouping columns.

The current portfolio/report layer already reserves `buy_hold_return` and benchmark-relative fields in the summary schema, and `backtest-shared` already knows how to compute benchmark-relative metrics. The missing slice is consistent wiring across the batch/full-market reporting path and the single-symbol summary so the comparison fields are actually populated and surfaced.

## Scope

Implement a narrow portfolio-report comparison slice:

1. Populate hold-to-maturity comparison metrics in single-symbol and batch summaries.
2. Surface hold-to-maturity comparison fields in `symbol_performance.csv` and `strategy_performance.json`.
3. Extend the batch/full-market reporting path so optional benchmark inputs produce benchmark-relative summary fields, reusing the existing benchmark comparison helper.
4. Preserve `board` / `industry` / `industry_group` passthrough columns so same-industry comparisons remain available without new source tables.
5. Keep shared-cash benchmark-relative behavior consistent with the new batch/full-market summary wiring.

## Required Behavior

- `buy_hold_return` must be computed from the same available start/end window used by the symbol or strategy result, not from a separate universe.
- `excess_return_vs_buy_hold` should be populated when both strategy return and buy-and-hold return are available.
- `information_ratio_vs_buy_hold` should be populated where the report schema already expects it.
- `backtest-batch` should accept optional benchmark comparison inputs and, when provided, emit benchmark-relative summary values through the existing reporting path.
- `backtest-shared` must keep its current benchmark-relative behavior and should not lose the existing summary fields.
- Industry metadata should continue flowing through existing report rows and grouped summaries without introducing a new industry source or a new producer dependency.
- Keep the implementation read-only and consumer-side only. Do not add new Tushare producer code or touch `quant_ts`.

## Suggested Implementation Notes

- Reuse the existing benchmark-relative helper in `src/quant_research_engine/portfolio/benchmark.py`.
- Populate buy-and-hold metrics at the lowest level that already has symbol-specific price history, then aggregate upward through `portfolio/batch.py` and `portfolio/full_market_report.py`.
- Keep `portfolio/full_market_report.py` as the final report assembly layer; do not duplicate comparison math there if it can be derived earlier.
- Preserve existing manifest roles and filenames; this slice is about content wiring, not report shape redesign.
- If benchmark inputs are absent, leave benchmark-relative fields null rather than fabricating a fallback.

## Non-Goals

- Do not implement real regime classification.
- Do not add new data ingestion or producer-side code.
- Do not rewrite strategy execution semantics.
- Do not redesign the reporting format or manifest schema.
- Do not add new industry source tables or a new industry comparison engine.

## Expected Tests

Add or update targeted tests in:

- `tests/test_portfolio_single_symbol.py`
- `tests/test_portfolio_batch.py`
- `tests/test_full_market_report.py`
- `tests/test_cli.py`
- `tests/test_portfolio_benchmark.py`

Targeted coverage should prove:

- single-symbol summaries emit buy-and-hold baseline fields;
- batch summaries aggregate buy-and-hold metrics consistently;
- benchmark-relative summary fields appear when benchmark inputs are supplied;
- industry metadata still flows through symbol/performance rows;
- existing shared-cash benchmark-relative behavior is preserved.

## Validation Commands

Run at minimum:

```bash
uv run pytest -q tests/test_portfolio_single_symbol.py tests/test_portfolio_batch.py
uv run pytest -q tests/test_full_market_report.py tests/test_cli.py tests/test_portfolio_benchmark.py
scripts/check-progress-docs.sh
git diff --check
```

If time permits:

```bash
uv run pytest -q
```

## Acceptance Criteria

- Buy-and-hold comparison fields are populated in portfolio summaries instead of remaining null.
- Batch/full-market reports can surface benchmark-relative comparison fields when benchmark inputs are provided.
- Industry metadata remains available for same-industry comparison through existing summary/grouping columns.
- Existing shared-cash benchmark comparison continues to work.
- Targeted tests pass.
- Progress docs and handoff files are updated by Claude Code after implementation.
