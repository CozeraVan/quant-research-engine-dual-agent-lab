# Coding Handoff

## Task ID

QRE-STRATEGY-FIT-ANALYSIS-001 (M10.1, CR-0003 F3 phase 1)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + real-batch verification; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **New module** `analysis/strategy_fit.py` (~460 lines): exact one-sided binomial test (`math.lgamma`), hypergeometric enrichment, BH-FDR, batch loading from `batch_summary.json` + per-strategy `summary.csv`, significance-tier analysis (90%/99%/99.9%), magnitude gate (total_return > 0 AND excess_return_vs_buy_hold > 0), free-rider accounting, strategy meta-test vs false-positive expectation, class enrichment on the significant pool, global BH q-values, deterministic writers (`strategy_fit_summary/stocks/classes.csv` + `strategy_fit_report.md` + `report_manifest.json`).
2. **Manifest integration**: `strategy_fit_report_manifest` registered in `_SUPPORTED_MANIFEST_KINDS`; required-column contracts for the three CSV roles in `_REQUIRED_COLUMNS_BY_ROLE`; `qre report-audit` passes on real output.
3. **Script** `scripts/strategy_fit_report.py`: batch-dir input, tiers/pool-tier/min-trades/min-class-size/metadata-as-of options, read-only metadata composition, progress output.
4. **Runner passthrough**: `--metadata-columns` threaded `BatchRunConfig` → `ResearchRunRequest.metadata_columns` for future batches to embed class columns in summary.csv.
5. **Metadata reality handled**: `reference.stock_basic` discovered EMPTY upstream (0 rows; `daily_basic`/`index_weight`/`stock_suspend`/`index_daily`/`trade_calendar` populated). Script composes metadata from `daily_basic` snapshot (market_cap_bucket/liquidity_bucket) + `derive_board(ts_code)`; `industry_group` → `unknown` until upstream populates `stock_basic` (noted in report caveats).
6. **Tests** `tests/test_strategy_fit.py` (11): exact binomial/hypergeometric known values, BH ordering, tier/gate/free-rider accounting, no-edge strategy correctly judged ineffective, noise-only strategy → empty pool, enrichment concentration detection, unknown metadata bucket, batch load skips, end-to-end outputs + `ReportManifest.from_path` content validation with zero issues.

## Files Changed

- `src/quant_research_engine/analysis/__init__.py` (new), `src/quant_research_engine/analysis/strategy_fit.py` (new)
- `src/quant_research_engine/portfolio/report_manifest.py` (kind + roles registration)
- `src/quant_research_engine/orchestration/batch_runner.py` (`metadata_columns` passthrough)
- `scripts/strategy_fit_report.py` (new), `scripts/batch_backtest_runner.py` (`--metadata-columns`)
- `tests/test_strategy_fit.py` (new, 11 tests)

## Validation Output

```bash
uv run pytest tests/test_strategy_fit.py -q → 11 passed
uv run pytest -q → 1045 passed, 4 warnings (1034 baseline + 11 new)
uv run python scripts/strategy_fit_report.py --batch-dir outputs/backtests/quick_batch_106/f365c8a07b33
  → 106 analyzed, 5 skipped; metadata 5,256 symbols (daily_basic + derive_board)
uv run qre report-audit outputs/strategy_fit/f365c8a07b33/report_manifest.json --require-match
  → missing_files=0, validation_issues=0, status=ok
```

## Real-Batch Finding (screening evidence, R-QRE-008)

- All 106 catalog strategies land BELOW the 90% meta tier for 2024: significant-stock counts are systematically LOWER than the false-positive expectation at every tier (e.g. mr04a: 79 observed vs 122.3 expected at 90%) — per-symbol win rates skew below 50% market-wide in this window, consistent with the batch's near-zero/negative mean excess.
- Candidates survive individually: 25 stocks across strategies reach the 99% tier (e.g. bo06a/688109.SH, bo04a/600148.SH with 44% excess); mr04a pool mean excess +29.8%, cs01a +75.9% — recorded in `strategy_fit_stocks.csv` as leads, NOT conclusions.
- Single-year window caveat: 2024 (Jan-Feb crash + Sep-24 rally) is hostile to most technical strategies; the framework correctly separated "looks good" from "statistically holds".
