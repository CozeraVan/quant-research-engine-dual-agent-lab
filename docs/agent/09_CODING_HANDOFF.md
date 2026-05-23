# Coding Handoff

## Task ID

QRE-FULL-MARKET-CHARTS-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Objective

Add equity curve and drawdown chart visualizations to the full-market report Excel workbook and as standalone PNG files.

## Implementation Summary

- `pyproject.toml` — added `matplotlib>=3.7.0` to dependencies.
- `src/quant_research_engine/portfolio/full_market_report.py`:
  - `generate_equity_curve_chart(equity, output_path) -> Path | None` — dual-axis chart: total_equity (left, blue), cumulative_return (right, orange). A4 width, 4" height, dpi=150. Uses `matplotlib.use("Agg")`. Returns None if equity is empty or missing required columns.
  - `generate_drawdown_chart(drawdown, output_path) -> Path | None` — filled area of drawdown_pct (red, alpha=0.25 fill, 0.8 line). A4 width, 3.2" height, dpi=150. Returns None if empty or missing columns.
  - `write_full_market_excel()` — added keyword-only parameters `equity_curve_chart: Path | None = None` and `drawdown_curve_chart: Path | None = None`. When provided and file exists, creates `EquityCurveChart` and `DrawdownCurveChart` sheets with embedded PNG images (820×310px and 820×250px). Artifacts sheet includes chart entries.
  - `write_full_market_report()` — both batch and shared_cash branches generate charts after capital_usage, conditionally add to paths dict, and pass to `write_full_market_excel()`.
- `src/quant_research_engine/portfolio/io.py`:
  - `_shared_manifest_role()` — maps `equity_curve_chart` → `"equity_curve_chart"`, `drawdown_curve_chart` → `"drawdown_curve_chart"`.
  - `_batch_manifest_role()` — same mappings.
  - `_shared_report_paths()` and `_batch_report_paths()` — include chart labels.
- `src/quant_research_engine/portfolio/report_manifest.py` — `_REQUIRED_COLUMNS_BY_ROLE` includes `"equity_curve_chart": set()` and `"drawdown_curve_chart": set()` (no CSV column validation for PNG roles).
- `tests/test_full_market_report.py` — 10 new tests:
  - `TestGenerateEquityCurveChart` (3): valid generates PNG, empty returns None, missing columns returns None.
  - `TestGenerateDrawdownChart` (3): valid generates PNG, empty returns None, missing columns returns None.
  - `TestWriteFullMarketExcel` (+2): embeds chart sheets when provided, skips when None.
  - `TestWriteFullMarketReport` (+1): chart artifacts in batch paths.
  - `TestWriteFullMarketReportSharedCash` (+1): chart artifacts in shared_cash paths.

## Validation

```bash
uv run pytest tests/test_full_market_report.py -q
# 50 passed (was 40, +10 new)

uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_full_market_report.py tests/test_research_run.py -q
# 529 passed, 2 warnings in 12.83s

scripts/check-progress-docs.sh
# pending doc sync

git diff --check
# pending
```
