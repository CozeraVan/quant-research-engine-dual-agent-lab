# Coding Handoff

## Task ID

QRE-PARAM-OVERRIDE-001 (M10.2a, CR-0003 F1a part 1)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + small-sample verification; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **`portfolio/universe.py`** (new):
   - `load_universe_metadata()`: per-symbol availability table from populated sources — `is_suspended` (latest `reference.stock_suspend` record ≤ as_of, type S/R), `is_st`/`is_risk_warning` (latest `reference.stock_st` ≤ as_of; risk-warning mapped to ST board per A-share practice), `list_date` (derived from first bar in `public.stock_daily`). Each source independently optional.
   - `apply_universe_filter()`: symbol-level filtering with complete accounting — every applied rule appears in `dropped_by_rule` (zero counts included); a rule whose data is entirely unavailable lands in `unavailable_rules` and drops NOTHING (never silently skipped, never silently dropped).
   - `validate_profile_overrides()`: whitelist + non-negative validation for cost overrides.
2. **research_run wiring**: `ResearchRunRequest.profile_overrides` (applied via `dataclasses.replace` after profile load) and `universe_filter` (default False — explicit opt-in, no silent change). When enabled, the spec's `universe:` fields are applied to the assembled frame before the engine (both batch and shared modes); `universe_report.json` written as a backtest artifact and registered in `paths`; `research_run_manifest.json` records `profile_overrides` and `universe_filter`.
3. **Runner**: `--universe-filter`, `--commission-rate`, `--min-commission`, `--stamp-tax`, `--transfer-fee`, `--slippage-buy`, `--slippage-sell`; threaded `BatchRunConfig` → `ResearchRunRequest`; echoed into `batch_summary.json` config.
4. **Tests** `tests/test_universe.py` (14): override validation, each universe rule independently + edge cases (exact listing-day cutoff, unknown-flag kept, missing amount column → unavailable + keep), combined-rule union accounting, unavailable-not-dropped, passthrough when no rules, research_run override application/rejection, universe filter applied/recorded/off-by-default, manifest fields, runner passthrough.

## Files Changed

- `src/quant_research_engine/portfolio/universe.py` (new)
- `src/quant_research_engine/orchestration/research_run.py` (overrides + universe filter + manifest fields)
- `src/quant_research_engine/orchestration/batch_runner.py` (config fields + threading)
- `scripts/batch_backtest_runner.py` (new flags + config echo)
- `tests/test_universe.py` (new, 14 tests)

## Validation Output

```bash
uv run pytest tests/test_universe.py -q → 14 passed
uv run pytest -q → 1059 passed, 4 warnings (1045 baseline + 14 new)

# R-QRE-009 small-sample real-DB check (3 symbols, smoke window):
#   - slippage/commission overrides → summaries measurably differ ✓
#   - universe_report.json: applied=true, 3/3 kept, drops counted,
#     exclude_st/exclude_risk_warning honestly 'unavailable' (no stock_st records ≤ 2024-01-01),
#     exclude_suspended/min_listing_days available ✓
#   - research_run_manifest records profile_overrides + universe_filter ✓
```

## Scope Note

Stop-loss/take-profit for the batch path is split to **M10.2b** (new engine exit logic requiring dual-engine equality work — simulator + vectorized must both change and re-verify). This slice changes NO engine behavior; default runs are bit-identical to before.
