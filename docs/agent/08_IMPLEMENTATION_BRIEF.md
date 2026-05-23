# Implementation Brief

## Task ID

QRE-FULL-MARKET-CHARTS-001

## Created By

CLAUDE_CODE (acting planner — Codex unavailable)

## Intended Implementer

CLAUDE_CODE

## Goal

Add equity curve and drawdown chart visualizations to the full-market report Excel workbook and as standalone PNG files. Both batch and shared_cash engine modes get identical chart logic.

## Approach

Add `matplotlib` dependency. Create two chart generator functions that produce PNG files using the Agg backend. Embed PNGs as new Excel sheets via `openpyxl.drawing.image.Image` and save as standalone files. Both `engine_mode` branches get identical chart generation logic.

## Required Changes

1. `pyproject.toml` — add `matplotlib>=3.7.0` dependency
2. `src/quant_research_engine/portfolio/full_market_report.py` — add `generate_equity_curve_chart()` and `generate_drawdown_chart()` functions; modify `write_full_market_excel()` signature with keyword-only chart parameters; embed chart sheets; generate charts in both engine_mode branches
3. `src/quant_research_engine/portfolio/io.py` — register chart roles in manifest and report paths helpers
4. `src/quant_research_engine/portfolio/report_manifest.py` — add chart roles to `_REQUIRED_COLUMNS_BY_ROLE`
5. `tests/test_full_market_report.py` — 10 new tests
6. Agent docs: all doc files synced

## Validation Commands

```bash
uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_full_market_report.py tests/test_research_run.py -q
scripts/check-progress-docs.sh
git diff --check
```
