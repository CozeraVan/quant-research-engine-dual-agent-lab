# Agent Board

## Current Task ID

QRE-FULL-MARKET-CHARTS-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_REQUEST

## Sender

CLAUDE_CODE (acting planner — Codex unavailable)

## Short Message

Add equity curve and drawdown chart visualizations to the full-market report Excel workbook and as standalone PNG files. Uses matplotlib Agg backend for chart generation and openpyxl image embedding for Excel integration. Both batch and shared_cash engine modes get identical chart logic.

## Delivered Artifacts

- `pyproject.toml` — added `matplotlib>=3.7.0` dependency
- `src/quant_research_engine/portfolio/full_market_report.py` — `generate_equity_curve_chart()` + `generate_drawdown_chart()` functions; modified `write_full_market_excel()` signature with keyword-only chart parameters; embedded chart sheets; both engine_mode branches generate charts
- `src/quant_research_engine/portfolio/io.py` — `equity_curve_chart` + `drawdown_curve_chart` roles in `_shared_manifest_role()`, `_batch_manifest_role()`, `_shared_report_paths()`, `_batch_report_paths()`
- `src/quant_research_engine/portfolio/report_manifest.py` — chart roles added to `_REQUIRED_COLUMNS_BY_ROLE` with empty `set()`
- `tests/test_full_market_report.py` — 10 new tests: `TestGenerateEquityCurveChart` (3), `TestGenerateDrawdownChart` (3), `TestWriteFullMarketExcel` chart methods (2), `TestWriteFullMarketReport.test_generates_chart_artifacts` (1), `TestWriteFullMarketReportSharedCash.test_generates_chart_artifacts` (1)

## Validation

```bash
uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_full_market_report.py tests/test_research_run.py -q
scripts/check-progress-docs.sh
git diff --check
```

## Next Step

Claude Code implements, self-reviews, updates agent docs, then hands off for git finalization.
