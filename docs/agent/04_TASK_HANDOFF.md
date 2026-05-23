# Task Handoff

## Current Task

Add equity curve and drawdown chart visualizations to the full-market report Excel workbook and as standalone PNG files.

## Task ID

QRE-FULL-MARKET-CHARTS-001

## Current Status

FINALIZED in commit `a86018d`. Claude Code has completed full-market report charts: `generate_equity_curve_chart()` and `generate_drawdown_chart()` functions added; chart PNGs embedded in Excel workbook as new sheets; both batch and shared_cash engine modes produce charts; manifest roles and required columns registered; 10 new tests pass (529 total).

## Current Owner

CLAUDE_CODE

## Completed

- Full-market report charts implemented:
  - `pyproject.toml` — added `matplotlib>=3.7.0` dependency
  - `src/quant_research_engine/portfolio/full_market_report.py` — `generate_equity_curve_chart()` (dual-axis: total_equity + cumulative_return, A4 width, 4" height, dpi=150) and `generate_drawdown_chart()` (filled area of drawdown_pct, A4 width, 3.2" height, dpi=150) added. Both use `matplotlib.use("Agg")` and return `Path | None`. Modified `write_full_market_excel()` signature with keyword-only `equity_curve_chart` and `drawdown_curve_chart` parameters; embedded chart PNGs as `EquityCurveChart` and `DrawdownCurveChart` sheets via `openpyxl.drawing.image.Image`; added chart entries to Artifacts sheet. Both batch and shared_cash branches in `write_full_market_report()` generate charts after capital_usage and conditionally include in paths dict.
  - `src/quant_research_engine/portfolio/io.py` — `_shared_manifest_role()` and `_batch_manifest_role()` map `equity_curve_chart` → `"equity_curve_chart"` and `drawdown_curve_chart` → `"drawdown_curve_chart"`. `_shared_report_paths()` and `_batch_report_paths()` include chart labels.
  - `src/quant_research_engine/portfolio/report_manifest.py` — `_REQUIRED_COLUMNS_BY_ROLE` includes `"equity_curve_chart": set()` and `"drawdown_curve_chart": set()`.
  - `tests/test_full_market_report.py` — 10 new tests:
    - `TestGenerateEquityCurveChart` (3): valid data generates PNG, empty returns None, missing columns returns None.
    - `TestGenerateDrawdownChart` (3): valid data generates PNG, empty returns None, missing columns returns None.
    - `TestWriteFullMarketExcel` (2): `test_embeds_chart_images_when_provided`, `test_skips_chart_sheets_when_not_provided`.
    - `TestWriteFullMarketReport` (1): `test_generates_chart_artifacts` — batch mode chart artifacts in paths.
    - `TestWriteFullMarketReportSharedCash` (1): `test_generates_chart_artifacts` — shared_cash mode chart artifacts in paths.
  - 529 tests pass, no regressions.

## Scope Notes

- Charts use matplotlib Agg backend (non-interactive) and are embedded as PNG images in the Excel workbook.
- Both chart functions return `Path | None` — None signals "no chart generated" (empty data or missing columns).
- `write_full_market_excel()` uses keyword-only parameters (`*` separator) for backward-compatible signature changes.
- Chart image dimensions in Excel: equity curve 820×310px, drawdown curve 820×250px.
- Equity curve chart: dual-axis with total_equity (left, blue #1f77b4) and cumulative_return (right, orange #ff7f0e).
- Drawdown chart: filled area (red #d62728, alpha=0.25) with line overlay.

## Validation Baseline

```bash
uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_full_market_report.py tests/test_research_run.py -q
scripts/check-progress-docs.sh
git diff --check
```

Current results: 529 passed, 2 warnings (pre-existing numpy) in 12.83s.
