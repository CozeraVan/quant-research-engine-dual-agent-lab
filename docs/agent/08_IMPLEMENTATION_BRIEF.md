# Implementation Brief

## Task ID

QRE-SHARED-CASH-FULL-MARKET-REPORT-001

## Created By

CLAUDE_CODE (acting planner — Codex unavailable)

## Intended Implementer

CLAUDE_CODE

## Goal

Add shared-cash support to `write_full_market_report()` and wire it into `write_shared_cash_result()` so that `qre research-run --backtest-mode shared` produces the same full-market report bundle as batch mode.

## Approach

Add `engine_mode: str = "batch"` parameter to all builders and the entry point. Shared-cash paths read flat DataFrames (orders, trades, equity_curve) instead of `dict[str, SingleSymbolBacktestResult]`. Use `full_market_equity_curve` key to avoid collision with shared-cash's existing `equity_curve` entry.

## Required Changes

1. `src/quant_research_engine/portfolio/full_market_report.py` — add `engine_mode` parameter to 6 functions; shared-cash branches read flat DataFrames; `failed_orders` param for correct failed order counting
2. `src/quant_research_engine/portfolio/io.py` — call `write_full_market_report()` with `engine_mode="shared_cash"` in `write_shared_cash_result()`; update `_shared_manifest_role()` and `_shared_report_paths()`
3. Tests: 19 new tests (17 in test_full_market_report.py, 2 in test_portfolio_io.py)
4. Agent docs: all 10 doc files synced

## Validation Commands

```bash
uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_full_market_report.py tests/test_research_run.py -q
scripts/check-progress-docs.sh
git diff --check
```
