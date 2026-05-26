# Task Handoff

## Task ID

QRE-PORTFOLIO-BASELINE-COMPARISON-001

## Current Status

DONE

## Current Owner

CODEX

## Problem Summary

Portfolio reporting had a baseline-comparison gap:

- single-symbol summaries did not consistently emit buy-and-hold comparison fields;
- batch/full-market summary outputs reserved `buy_hold_return` and benchmark-relative fields, but the values were not wired through consistently;
- same-industry comparison was available through existing `industry` passthrough but `industry_group` was not included in batch metadata defaults;
- shared-cash benchmark-relative behavior already existed and remained unchanged.

The slice makes strategy comparison explicit at the reporting layer without changing execution semantics or adding any producer-side code.

## Implementation Completed By Claude Code

- `_build_summary()` in single_symbol.py now computes `buy_hold_return` from first entry price to last mark price and `excess_return_vs_buy_hold`.
- `_empty_result()` includes `buy_hold_return: None` and `excess_return_vs_buy_hold: None`.
- `run()` passes the working frame to `_build_summary()`.
- `industry_group` added to `SUMMARY_METADATA_COLUMNS` in batch.py.
- `summarize_batch_summary()` in analytics.py aggregates `buy_hold_return`, `mean_buy_hold_return`, `median_buy_hold_return`, `mean_excess_return_vs_buy_hold`, `median_excess_return_vs_buy_hold`.
- `backtest-batch` CLI now accepts `--benchmark-table`, `--benchmark-code`, `--benchmark-value-column` and wires benchmark-relative performance into `summary_metrics`.
- 8 new tests added across single_symbol, batch, analytics, and CLI test files.

## Hard Constraints

- No Tushare download, credential, sync, or ingestion code added to QRE.
- `../quant_ts` not modified.
- Portfolio execution semantics unchanged.
- No real regime classification or full time-varying/as-of metadata added.
- QRE remains read-only against upstream databases.

## Validation Evidence

```bash
uv run pytest -q tests/test_portfolio_single_symbol.py tests/test_portfolio_batch.py → 20 passed
uv run pytest -q tests/test_portfolio_analytics.py → 26 passed
uv run pytest -q tests/test_full_market_report.py tests/test_cli.py tests/test_portfolio_benchmark.py → 485 passed, 2 warnings
uv run pytest -q → 896 passed, 2 warnings
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Handoff Back To Codex

Review passed. Preserve the accepted baseline-comparison wiring and proceed with git finalization.
