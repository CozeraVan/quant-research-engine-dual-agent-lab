# Implementation Brief

## Task ID

QRE-PORTFOLIO-BENCHMARK-REPORT-ARTIFACTS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Propagate the already-computed benchmark-relative comparison fields into the full-market report artifacts so the batch reporting outputs, especially `strategy_performance.json`, expose the same benchmark context that `backtest-batch` prints to stdout. Keep the buy-and-hold comparison slice unchanged and preserve the existing industry passthrough behavior.

The benchmark math itself is already implemented. The missing slice is artifact propagation: make the report assembly layer carry the `benchmark_*` fields through to durable outputs without changing the underlying comparison semantics.

## Scope

Implement a narrow report-artifact propagation slice:

1. Thread benchmark-relative summary fields from batch `summary_metrics` into `portfolio/full_market_report.py`.
2. Surface benchmark-relative fields in `strategy_performance.json` and the full-market report views that are derived from it.
3. Preserve the current buy-and-hold comparison fields, shared-cash behavior, and industry metadata passthrough unchanged.
4. Keep the work consumer-side only. Do not touch `quant_ts`, Tushare download/ingest code, or any producer-side schema.

## Required Behavior

- If `benchmark_*` fields are present in batch `summary_metrics`, the report artifacts should carry them through verbatim.
- `strategy_performance.json` should include the benchmark comparison fields alongside the existing buy-and-hold metrics.
- The generated HTML/Excel report views should continue to read from the same strategy performance payload, so no separate benchmark math is duplicated in the renderer.
- If benchmark inputs are absent, report artifacts should omit or leave benchmark fields null without inventing fallback values.
- Shared-cash report behavior must remain unchanged.
- Existing buy-and-hold and industry metadata fields must continue to be present.

## Suggested Implementation Notes

- Reuse the benchmark summary fields already attached by `backtest-batch`; do not recompute benchmark math in the report layer.
- Extend `build_strategy_performance()` and any nearby helpers only as far as needed to pass through the existing `benchmark_*` keys.
- Keep `portfolio/full_market_report.py` as the final report assembly layer.
- Preserve the current report manifest names and file layout.

## Non-Goals

- Do not implement new benchmark comparison math.
- Do not change single-symbol, batch-summary, or shared-cash execution semantics.
- Do not redesign the report schema or add new output files.
- Do not add new data ingestion or producer-side code.
- Do not touch `quant_ts`.

## Expected Tests

Add or update targeted tests in:

- `tests/test_full_market_report.py`

Targeted coverage should prove:

- the workbook `Performance` sheet is populated from strategy performance data;
- benchmark fields appear in the workbook when benchmark inputs are supplied;
- buy-and-hold and shared-cash paths remain unchanged;
- the report artifact outputs still validate end to end.

## Validation Commands

Run at minimum:

```bash
uv run pytest -q tests/test_full_market_report.py
scripts/check-progress-docs.sh
git diff --check
```

If time permits:

```bash
uv run pytest -q
```

## Acceptance Criteria

- Full-market report artifacts expose the benchmark-relative summary fields already computed by `backtest-batch`.
- `strategy_performance.json` carries the benchmark section without changing the existing buy-and-hold fields.
- Shared-cash and benchmark math behavior remain unchanged.
- Targeted tests pass.
- Progress docs and handoff files are updated by Claude Code after implementation.
